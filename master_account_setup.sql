-- Master Account & RBAC Setup

-- 1. Create Profiles table (extending Auth)
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID REFERENCES auth.users ON DELETE CASCADE PRIMARY KEY,
  email TEXT,
  is_admin BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Create trigger to sync Auth user to Profiles
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, email)
  VALUES (new.id, new.email);
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- 3. Backfill existing users into profiles (if any)
INSERT INTO public.profiles (id, email)
SELECT id, email FROM auth.users
ON CONFLICT (id) DO NOTHING;

-- 4. Set specific user as Admin (REPLACE WITH USER ID LATER)
-- UPDATE public.profiles SET is_admin = true WHERE email = 'your-email@example.com';

-- 5. Enable RLS on auction_items (if not already enabled)
ALTER TABLE public.auction_items ENABLE ROW LEVEL SECURITY;

-- 6. Update Policies to allowed Admin access
DROP POLICY IF EXISTS "Users can only see their own auction items" ON public.auction_items;
DROP POLICY IF EXISTS "Admin can see everything" ON public.auction_items;
DROP POLICY IF EXISTS "Users can view their own auctions" ON public.auction_items;

-- Select Policy
CREATE POLICY "Users can view their own auctions" ON public.auction_items
  FOR SELECT USING (
    auth.uid() = user_id OR 
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND is_admin = true)
  );

-- All other operations (INSERT/UPDATE/DELETE)
CREATE POLICY "Users can manage their own auctions" ON public.auction_items
  FOR ALL USING (
    auth.uid() = user_id OR 
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND is_admin = true)
  );

-- 7. Add Realtime for profiles to dashboard
ALTER PUBLICATION supabase_realtime ADD TABLE profiles;
