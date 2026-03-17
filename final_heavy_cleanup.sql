-- SQL CLEANUP & FINAL FIX
-- This script drops ALL redundant and buggy audit triggers and establishes a clean state.

-- 1. DROP ALL POTENTIALLY BUGGY TRIGGERS
DROP TRIGGER IF EXISTS trg_audit_auction_items ON public.auction_items;
DROP TRIGGER IF EXISTS auction_items_audit_trigger ON public.auction_items;
DROP TRIGGER IF EXISTS audit_auction_items ON public.auction_items;
DROP TRIGGER IF EXISTS tr_auction_items_site_detection ON public.auction_items;

-- 2. FIX THE AUDIT FUNCTION (The one with the bug)
CREATE OR REPLACE FUNCTION public.auction_items_audit_trigger()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
AS $function$
DECLARE
  audited_cols text[] := ARRAY['id','item_name','status','user_id','url'];
  ignore_cols  text[] := ARRAY['locked_until','next_fetch_at','last_scraped_at'];
  c text;
  actor_uid uuid;
  before_json jsonb := '{}'::jsonb;
  after_json  jsonb := '{}'::jsonb;
  v_changed_count int;
BEGIN
  -- Attempt to get actor ID
  BEGIN
    actor_uid := (SELECT auth.uid());
  EXCEPTION WHEN others THEN
    actor_uid := NULL;
  END;

  IF (TG_OP = 'INSERT') THEN
    FOR c IN SELECT unnest(audited_cols) LOOP
      IF to_jsonb(NEW) ? c THEN
        after_json := after_json || jsonb_build_object(c, to_jsonb(NEW) -> c);
      END IF;
    END LOOP;

    -- Correct way to count keys (Avoid SRF in COALESCE)
    v_changed_count := (SELECT count(*) FROM jsonb_object_keys(after_json))::int;

    INSERT INTO audit.audit_log(id, occurred_at, who, user_email, schema_name, table_name, record_id, operation, data_before, data_after, changed_fields, short_message, changed_count)
    VALUES (gen_random_uuid(), now(), actor_uid, NULL, TG_TABLE_SCHEMA, TG_TABLE_NAME, (NEW.id)::text, 'INSERT', NULL, after_json, ARRAY[]::text[], format('Inserted %s', COALESCE((NEW.item_name)::text, (NEW.id)::text)), v_changed_count);

    RETURN NEW;
  
  ELSIF (TG_OP = 'UPDATE') THEN
    FOR c IN SELECT unnest(audited_cols) LOOP
      IF (to_jsonb(OLD) ->> c) IS DISTINCT FROM (to_jsonb(NEW) ->> c) THEN
        IF NOT (c = ANY(ignore_cols)) THEN
          before_json := before_json || jsonb_build_object(c, to_jsonb(OLD) -> c);
          after_json  := after_json  || jsonb_build_object(c, to_jsonb(NEW) -> c);
        END IF;
      END IF;
    END LOOP;

    v_changed_count := (SELECT count(*) FROM jsonb_object_keys(after_json))::int;
    IF v_changed_count = 0 THEN RETURN NEW; END IF;

    INSERT INTO audit.audit_log(id, occurred_at, who, user_email, schema_name, table_name, record_id, operation, data_before, data_after, changed_fields, short_message, changed_count)
    VALUES (gen_random_uuid(), now(), actor_uid, NULL, TG_TABLE_SCHEMA, TG_TABLE_NAME, (NEW.id)::text, 'UPDATE', before_json, after_json, ARRAY(SELECT jsonb_object_keys(after_json)), format('Updated %s', COALESCE((NEW.item_name)::text, (NEW.id)::text)), v_changed_count);

    RETURN NEW;
  END IF;

  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$function$;

-- 3. ESTABLISH CLEAN TRIGGERS
-- Site Detection (Critical for your app)
CREATE TRIGGER tr_auction_items_site_detection
BEFORE INSERT ON public.auction_items
FOR EACH ROW
EXECUTE FUNCTION public.handle_auction_item_site_detection();

-- Unified Audit Trigger (Optional but fixed now)
CREATE TRIGGER trg_audit_auction_items
AFTER INSERT OR UPDATE OR DELETE ON public.auction_items
FOR EACH ROW
EXECUTE FUNCTION public.auction_items_audit_trigger();
