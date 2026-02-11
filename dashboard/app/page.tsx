"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { createClient } from "@/utils/supabase-browser";
import { useRouter } from "next/navigation";
import { getInitialPremium, getSiteKey } from "@/utils/constants";
import {
  Plus,
  Search,
  LogOut,
  LayoutGrid,
  Clock,
  Gavel,
  MapPin,
  Trash2,
  Play,
  Pause,
  Filter,
  ArrowUpDown,
  ExternalLink,
  RefreshCw,
  TrendingUp,
  Users,
  Volume2,
  VolumeX,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface User {
  id: string;
  email?: string;
}

interface Auction {
  id: string;
  item_name?: string;
  current_bid?: number;
  premium_percentage?: number;
  total_bidders?: number;
  time_remaining_str?: string;
  city?: string;
  state?: string;
  serial_number?: string;
  website_name?: string;
  url: string;
  site_key?: string;
  closing_time?: string;
  status: "active" | "paused" | "pending" | "error" | "expired";
  locked_until?: string | null;
}

interface RealtimeUpdatePayload {
  eventType: "INSERT" | "UPDATE" | "DELETE";
  new: Auction;
  old: { id: string };
}

export default function Dashboard() {
  const [user, setUser] = useState<User | null>(null);
  const [auctions, setAuctions] = useState<Auction[]>([]);
  const [newUrl, setNewUrl] = useState("");
  const [addingItem, setAddingItem] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<
    "all" | "active" | "ended" | "paused"
  >("all");
  const [activeSource, setActiveSource] = useState("All Auctions");
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const buzzedItems = useRef<Set<string>>(new Set());
  const lastBuzzerTime = useRef<number>(0);
  const router = useRouter();
  // CRITICAL: Initialize supabase once, do NOT create on every render
  const [supabase] = useState(() => createClient());

  const fetchAuctions = useCallback(
    async (userId: string) => {
      const { data } = await supabase
        .from("auction_items")
        .select("*")
        .eq("user_id", userId)
        .order("created_at", { ascending: false });

      if (data) setAuctions(data as Auction[]);
    },
    [supabase],
  );

  const handleManualRefresh = useCallback(async () => {
    if (!user) return;
    setIsRefreshing(true);
    await fetchAuctions(user.id);
    // Brief delay for visual feedback
    setTimeout(() => setIsRefreshing(false), 800);
  }, [user, fetchAuctions]);

  const handleRealtimeUpdate = useCallback(
    async (payload: RealtimeUpdatePayload) => {
      console.log("🔔 Realtime Event Received:", payload.eventType, payload);
      const { eventType, new: newRecord, old: oldRecord } = payload;

      if (eventType === "INSERT") {
        setAuctions((prev) => {
          // Prevent duplicates if item already exists
          if (prev.some((a) => a.id === newRecord.id)) return prev;
          return [newRecord, ...prev];
        });
      } else if (eventType === "UPDATE") {
        const targetId = newRecord.id || oldRecord.id;
        if (!targetId) return;

        // Realtime Update Handler
        console.log("🔄 Update params:", newRecord);
        setAuctions((prev) =>
          prev.map((a) => {
            if (a.id !== targetId) return a;

            // Merge the new data
            const updated = { ...a, ...newRecord };

            // FIX: Ensure blinker stops if lock is released or status changes to expired
            // If newRecord explicitly has locked_until as null, it will be in updated.
            // But if status flips to 'expired' or 'active' due to finish, we want to be sure.
            if (newRecord.status === "expired") {
              updated.locked_until = null;
            }
            return updated;
          }),
        );
      } else if (eventType === "DELETE") {
        setAuctions((prev) => prev.filter((a) => a.id !== oldRecord.id));
      }
    },
    [supabase],
  );

  const playBuzzer = useCallback(() => {
    if (!soundEnabled) return;

    // Cooldown check (Ref-based to avoid render loops)
    const now = Date.now();
    if (now - lastBuzzerTime.current < 10000) return;
    lastBuzzerTime.current = now;

    const AudioContextClass =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    if (!AudioContextClass) return;

    const audioCtx = new AudioContextClass();

    // Create a Layered Siren (Realistic Emergency Tone)
    const playEmergencySiren = () => {
      const duration = 2.5;
      const startTime = audioCtx.currentTime;

      const createOsc = (
        type: OscillatorType,
        baseFreq: number,
        volume: number,
      ) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.type = type;

        // frequency sweep (low to high to low)
        osc.frequency.setValueAtTime(baseFreq, startTime);
        osc.frequency.exponentialRampToValueAtTime(
          baseFreq * 2.5,
          startTime + 0.6,
        );
        osc.frequency.exponentialRampToValueAtTime(baseFreq, startTime + 1.2);
        osc.frequency.exponentialRampToValueAtTime(
          baseFreq * 2.5,
          startTime + 1.8,
        );
        osc.frequency.exponentialRampToValueAtTime(baseFreq, startTime + 2.4);

        gain.gain.setValueAtTime(0, startTime);
        gain.gain.linearRampToValueAtTime(volume, startTime + 0.1);
        gain.gain.linearRampToValueAtTime(volume, startTime + 2.2);
        gain.gain.exponentialRampToValueAtTime(0.0001, startTime + 2.5);

        osc.connect(gain);
        gain.connect(audioCtx.destination);
        return osc;
      };

      // Layer 1: The "Gritty" base (Square Wave)
      const osc1 = createOsc("square", 140, 0.08);
      // Layer 2: The "Sharp" alert (Sawtooth Wave)
      const osc2 = createOsc("sawtooth", 280, 0.04);

      osc1.start(startTime);
      osc2.start(startTime);
      osc1.stop(startTime + duration);
      osc2.stop(startTime + duration);
    };

    playEmergencySiren();
  }, [soundEnabled]);

  const [tick, setTick] = useState(0);

  useEffect(() => {
    // Tick is used to trigger re-renders for the live countdown
    const timer = setInterval(() => setTick((prev) => prev + 1), 1000);

    // Safety Backup: Refresh full list every 60 seconds just in case Realtime hangs
    const safetyTimer = setInterval(() => {
      if (user) fetchAuctions(user.id);
    }, 60000);

    return () => {
      clearInterval(timer);
      clearInterval(safetyTimer);
    };
  }, [user, fetchAuctions]);

  // Monitor for critical items and buzz
  useEffect(() => {
    if (!soundEnabled) return;

    const now = new Date().getTime();
    let hasNewCritical = false;

    auctions.forEach((auction) => {
      if (!auction.closing_time || auction.status === "expired") return;

      const end = new Date(auction.closing_time).getTime();
      const diff = end - now;

      // Critical = < 10 mins (600,000 ms)
      if (diff > 0 && diff <= 600000) {
        if (!buzzedItems.current.has(auction.id)) {
          hasNewCritical = true;
          buzzedItems.current.add(auction.id);
        }
      } else if (diff > 600000 || diff <= 0) {
        // Reset buzzer status if it leaves critical zone or ends
        if (buzzedItems.current.has(auction.id)) {
          buzzedItems.current.delete(auction.id);
        }
      }
    });

    if (hasNewCritical) {
      playBuzzer();
    }
  }, [tick, auctions, soundEnabled, playBuzzer]);

  const getRemainingTime = (
    closingTime: string | undefined,
    staticStr: string | undefined,
    status: string | undefined,
  ) => {
    // Priority 1: If backend says expired, it's ended.
    if (status === "expired") return "Ended";

    if (!closingTime) {
      // If we only have a static string, clean it up
      if (!staticStr) return "Syncing...";
      // Standardize common formats like "3 Days : 17 Hours" to "3d 17h"
      return staticStr
        .replace(/Days?/gi, "d")
        .replace(/Hours?/gi, "h")
        .replace(/Minutes?/gi, "m")
        .replace(/Seconds?/gi, "s")
        .replace(/\s*:\s*/g, " ")
        .trim();
    }

    const end = new Date(closingTime).getTime();
    const now = new Date().getTime();
    const diff = end - now;

    if (diff <= 0) return "Ended";

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);

    const parts = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0 || days > 0) parts.push(`${hours}h`);
    if (minutes > 0 || hours > 0 || days > 0) parts.push(`${minutes}m`);
    parts.push(`${seconds}s`);

    return parts.join(" ");
  };

  useEffect(() => {
    const checkUser = async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        router.push("/login");
      } else {
        setUser(session.user as User);
        fetchAuctions(session.user.id);
      }
    };
    checkUser();

    const channel = supabase
      .channel("schema-db-changes")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "auction_items" },
        (payload) => {
          console.log("🔄 Real-time Update Received:", payload);
          handleRealtimeUpdate(payload as unknown as RealtimeUpdatePayload);
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [router, supabase, fetchAuctions, handleRealtimeUpdate]);

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUrl || !user) return;

    // Duplicate Prevention Check
    const isDuplicate = auctions.some(
      (a) =>
        a.url.toLowerCase().trim().replace(/\/$/, "") ===
        newUrl.toLowerCase().trim().replace(/\/$/, ""),
    );

    if (isDuplicate) {
      alert("This URL is already being monitored!");
      setNewUrl("");
      return;
    }

    setAddingItem(true);

    const { data, error } = await supabase
      .from("auction_items")
      .insert([
        {
          url: newUrl,
          user_id: user.id,
          site_key: getSiteKey(newUrl),
          status: "active",
          item_name: "Syncing...",
          website_name: "Pending Sync",
          current_bid: 0,
          premium_percentage: getInitialPremium(newUrl),
          total_bidders: 0,
          closing_time: null,
          time_remaining_str: "Starting Sync...",
        },
      ])
      .select()
      .single();

    if (!error && data) {
      setAuctions((prev) => [data as Auction, ...prev]);
      setNewUrl("");
      setActiveSource("All Auctions");
      setActiveTab("all");
    } else if (error) {
      console.error("Add item error:", error);
      alert("Failed to add URL. Please try again.");
    }
    setAddingItem(false);
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  const handleDelete = async (id: string) => {
    console.log("Attempting to delete item:", id);

    // OPTIMISTIC UPDATE: Remove from state immediately
    const previousAuctions = [...auctions];
    setAuctions((prev) => prev.filter((a) => a.id !== id));

    // Perform actual delete
    const { error } = await supabase
      .from("auction_items")
      .delete()
      .eq("id", id);

    if (error) {
      console.error("Delete error:", error);
      // ROLLBACK on error
      setAuctions(previousAuctions);
      alert("Failed to delete item. Please try again.");
    } else {
      console.log("Item deleted successfully");
    }
  };

  const toggleStatus = async (id: string, currentStatus: string) => {
    const newStatus = currentStatus === "active" ? "paused" : "active";
    console.log(`Toggling status for ${id}: ${currentStatus} -> ${newStatus}`);

    // OPTIMISTIC UPDATE: Change status immediately
    const previousAuctions = [...auctions];
    setAuctions((prev) =>
      prev.map((a) =>
        a.id === id
          ? {
              ...a,
              status: newStatus as Auction["status"],
              // If resuming, show fetching state optimistically
              locked_until:
                newStatus === "active"
                  ? new Date(Date.now() + 60000).toISOString()
                  : a.locked_until,
            }
          : a,
      ),
    );

    // Perform actual update
    const { error } = await supabase
      .from("auction_items")
      .update({ status: newStatus })
      .eq("id", id);

    if (error) {
      console.error("Toggle status error:", error);
      // ROLLBACK on error
      setAuctions(previousAuctions);
      alert("Failed to update status. Please try again.");
    } else {
      console.log(`Status updated to ${newStatus} successfully`);
    }
  };

  const handleInstantRefresh = async (id: string, currentStatus: string) => {
    console.log(`Triggering instant refresh for ${id}`);

    // 1. Calculate a "now" timestamp in ISO format
    const now = new Date().toISOString();

    // 2. Perform update: Status to 'active', next_fetch_at to now, protect with lock
    const lockTime = new Date(Date.now() + 60000).toISOString();
    const { error } = await supabase
      .from("auction_items")
      .update({
        status: "active",
        next_fetch_at: now,
        locked_until: lockTime,
      })
      .eq("id", id);

    if (error) {
      console.error("Instant refresh error:", error);
      alert("Failed to trigger refresh. Please try again.");
    } else {
      // Optimistic update for visual feedback
      setAuctions((prev) =>
        prev.map((a) =>
          a.id === id
            ? {
                ...a,
                status: "active",
                locked_until: new Date(Date.now() + 60000).toISOString(), // Mock lock for immediate feedback
              }
            : a,
        ),
      );
    }
  };

  const handlePauseAll = async () => {
    if (!user) return;
    if (!confirm("Are you sure you want to PAUSE all active items?")) return;

    // Filter local active items first
    const activeItems = auctions.filter((a) => a.status === "active");
    if (activeItems.length === 0) return;

    // Update in Supabase
    const { error } = await supabase
      .from("auction_items")
      .update({ status: "paused", locked_until: null })
      .eq("user_id", user.id)
      .eq("status", "active");

    if (error) {
      console.error("Pause All Error:", error);
      alert("Failed to pause items.");
    } else {
      // Optimistic Update
      setAuctions((prev) =>
        prev.map((a) =>
          a.status === "active"
            ? { ...a, status: "paused", locked_until: null }
            : a,
        ),
      );
    }
  };

  const handleDeleteAll = async () => {
    if (!user) return;
    if (
      !confirm(
        "Are you sure you want to DELETE ALL items? This action cannot be undone.",
      )
    )
      return;

    const { error } = await supabase
      .from("auction_items")
      .delete()
      .eq("user_id", user.id);

    if (error) {
      console.error("Delete All Error:", error);
      alert("Failed to delete items.");
    } else {
      setAuctions([]);
      buzzedItems.current.clear();
    }
  };

  const filteredAuctions = auctions
    .filter((a) => {
      // 1. Search Filter (Safe for undefined names)
      const matchesSearch =
        (a.item_name?.toLowerCase().includes(searchQuery.toLowerCase()) ??
          true) ||
        (a.website_name?.toLowerCase().includes(searchQuery.toLowerCase()) ??
          true) ||
        searchQuery === "";

      // 2. Source Filter
      const matchesSource =
        activeSource === "All Auctions" || a.website_name === activeSource;

      // 3. Status Tab Filter
      const matchesTab =
        activeTab === "all" ||
        (activeTab === "active" && a.status === "active") ||
        (activeTab === "paused" && a.status === "paused") ||
        (activeTab === "ended" && a.status === "expired");

      return matchesSearch && matchesSource && matchesTab;
    })
    .sort((a, b) => {
      // Sort by Closing Time Descending (Future -> Past)
      // Treats 'syncing' items as far future to keep them at top
      const tA = a.closing_time
        ? new Date(a.closing_time).getTime()
        : Number.MAX_SAFE_INTEGER;
      const tB = b.closing_time
        ? new Date(b.closing_time).getTime()
        : Number.MAX_SAFE_INTEGER;

      return tB - tA;
    });

  return (
    <div className="dashboard-root">
      {/* Dynamic Background */}
      <div className="mesh-gradient"></div>

      <header className="premium-nav">
        <div className="nav-container">
          <div className="nav-left">
            <div className="app-logo">
              <LayoutGrid size={24} strokeWidth={2.5} />
              <span>AUCTIONBOT</span>
            </div>
          </div>

          <div className="nav-center">
            <div className="search-pill">
              <Search size={18} className="search-icon" />
              <input
                type="text"
                placeholder="Track your equipment..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          <div className="nav-right">
            <button
              onClick={handleManualRefresh}
              className={`icon-btn refresh ${isRefreshing ? "spinning" : ""}`}
              title="Manual Sync"
              disabled={isRefreshing}
            >
              <RefreshCw size={20} />
            </button>
            <div className="user-info">
              <div className="avatar">{user?.email?.[0].toUpperCase()}</div>
              <div className="user-details">
                <span className="email-label">{user?.email}</span>
                <span className="role-label">Procurement Admin</span>
              </div>
            </div>
            <button
              onClick={() => setSoundEnabled(!soundEnabled)}
              className={`icon-btn sound ${soundEnabled ? "active" : ""}`}
              title={soundEnabled ? "Mute Alert" : "Enable Sound Alert"}
            >
              {soundEnabled ? <Volume2 size={20} /> : <VolumeX size={20} />}
            </button>
            <button
              onClick={handleLogout}
              className="icon-btn logout"
              title="Sign Out"
            >
              <LogOut size={20} />
            </button>
          </div>
        </div>
      </header>

      <main className="main-content">
        <div className="content-inner">
          {/* Dashboard Hero / Stats */}
          <section className="dashboard-hero">
            <div className="hero-text">
              <h1>Live Monitoring</h1>
              <p>
                Tracking {auctions.length} medical equipment listings across 15+
                websites.
              </p>
            </div>

            <div className="auction-actions">
              <form onSubmit={handleAddItem} className="add-item-bar">
                <div className="input-with-icon">
                  <Plus size={20} className="i-plus" />
                  <input
                    type="text"
                    placeholder="Paste a new GSA, GovPlanet, or BidSpotter URL..."
                    value={newUrl}
                    onChange={(e) => setNewUrl(e.target.value)}
                  />
                </div>
                <button disabled={addingItem} className="submit-add">
                  {addingItem ? (
                    <RefreshCw className="animate-spin" size={18} />
                  ) : (
                    "Track Link"
                  )}
                </button>
              </form>

              <button
                onClick={() => {
                  setSoundEnabled(true);
                  playBuzzer();
                }}
                className="pill ghost test-buzzer-btn"
              >
                <Volume2 size={14} />
                Test Alarm Sound
              </button>

              <button
                onClick={handlePauseAll}
                className="pill ghost"
                title="Pause All Active Auctions"
              >
                <Pause size={14} />
                Pause All
              </button>

              <button
                onClick={handleDeleteAll}
                className="pill ghost danger"
                title="Delete ALL Auctions"
              >
                <Trash2 size={14} />
                Delete All
              </button>
            </div>
          </section>

          {/* Mega Tabs - Sources */}
          <div className="mega-tabs">
            {[
              "All Auctions",
              ...Array.from(
                new Set(
                  auctions
                    .filter((a) => a.website_name)
                    .map((a) => a.website_name!),
                ),
              ).sort(),
            ].map((source) => (
              <button
                key={source}
                onClick={() => setActiveSource(source)}
                className={`source-pill ${activeSource === source ? "active" : ""}`}
              >
                {source}
              </button>
            ))}
          </div>

          {/* Quick Filters - Status */}
          <div className="filter-shelf">
            <div className="filter-group">
              <button
                onClick={() => setActiveTab("all")}
                className={`pill ${activeTab === "all" ? "active" : ""}`}
              >
                All Items ({auctions.length})
              </button>
              <button
                onClick={() => setActiveTab("active")}
                className={`pill ${activeTab === "active" ? "active" : ""}`}
              >
                Active
              </button>
              <button
                onClick={() => setActiveTab("paused")}
                className={`pill ${activeTab === "paused" ? "active" : ""}`}
              >
                Paused
              </button>
              <button
                onClick={() => setActiveTab("ended")}
                className={`pill ${activeTab === "ended" ? "active" : ""}`}
              >
                Ended
              </button>
            </div>
            <div className="sort-group">
              <button className="pill ghost">
                <ArrowUpDown size={14} /> Time Remaining
              </button>
              <button className="pill ghost">
                <Filter size={14} /> Filters
              </button>
            </div>
          </div>

          {/* Auction Grid */}
          <div className="grid-container">
            <AnimatePresence mode="popLayout">
              {filteredAuctions.map((auction) => (
                <motion.div
                  key={auction.id}
                  layout
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.3 }}
                  className={`glass-card auction-card ${auction.status} ${
                    auction.status === "expired" ? "card-ended" : ""
                  } ${
                    auction.locked_until &&
                    new Date(auction.locked_until).getTime() > Date.now()
                      ? "is-fetching"
                      : ""
                  }`}
                >
                  <div className="card-top">
                    <div className="status-indicator">
                      {(() => {
                        const isTimeUp =
                          auction.closing_time &&
                          new Date(auction.closing_time).getTime() <
                            new Date().getTime();
                        const displayStatus =
                          auction.status === "expired" || isTimeUp
                            ? "expired"
                            : auction.status;
                        const label =
                          displayStatus === "expired"
                            ? "ENDED"
                            : displayStatus.toUpperCase();

                        const isFetching =
                          auction.locked_until &&
                          new Date(auction.locked_until).getTime() > Date.now();

                        return (
                          <>
                            <div
                              className={`dot ${isFetching ? "fetching" : displayStatus}`}
                            ></div>
                            <span>{isFetching ? "FETCHING..." : label}</span>
                          </>
                        );
                      })()}
                    </div>
                    <div className="card-actions">
                      <button
                        onClick={() =>
                          handleInstantRefresh(auction.id, auction.status)
                        }
                        className="action-btn btn-refresh"
                        title="Instant Refresh"
                      >
                        <RefreshCw size={16} />
                      </button>
                      <button
                        onClick={() =>
                          auction.status !== "expired" &&
                          toggleStatus(auction.id, auction.status)
                        }
                        className={`action-btn ${auction.status === "active" ? "pause" : "resume"}`}
                        title={
                          auction.status === "expired"
                            ? "Auction Ended"
                            : auction.status === "active"
                              ? "Pause"
                              : "Resume"
                        }
                        disabled={auction.status === "expired"}
                      >
                        {auction.status === "active" ? (
                          <Pause size={16} />
                        ) : (
                          <Play size={16} />
                        )}
                      </button>
                      <button
                        onClick={() => handleDelete(auction.id)}
                        className="action-btn delete"
                        title="Delete"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>

                  <div className="card-center">
                    <h2 className="item-title">
                      {auction.item_name || "Processing URL..."}
                    </h2>
                    <div className="meta-strip">
                      <div className="meta-pill">
                        <MapPin size={12} />
                        <span>
                          {(() => {
                            const city =
                              auction.city && auction.city !== "Unknown"
                                ? auction.city
                                : null;
                            const state =
                              auction.state && auction.state !== "Unknown"
                                ? auction.state
                                : null;
                            if (city && state) return `${city}, ${state}`;
                            if (city) return city;
                            if (state) return state;
                            return "Unknown";
                          })()}
                        </span>
                      </div>
                      <div className="meta-pill">
                        <Users size={12} />
                        <span>{auction.total_bidders || 0} Bidders</span>
                      </div>
                    </div>
                  </div>

                  <div className="stats-row">
                    <div className="stat-box">
                      <div className="stat-label">CURRENT BID</div>
                      <div className="stat-value small">
                        ${auction.current_bid?.toLocaleString() || "0.00"}
                      </div>
                    </div>
                    <div className="stat-box">
                      <div className="stat-label highlight">
                        <TrendingUp size={14} />
                        TOTAL PRICE (+{auction.premium_percentage || 0}%)
                      </div>
                      <div className="stat-value highlight">
                        $
                        {(
                          (auction.current_bid || 0) *
                          (1 + (auction.premium_percentage || 0) / 100)
                        ).toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </div>
                    </div>
                  </div>

                  <div className="card-bottom">
                    <div className="time-group">
                      <div className="time-left">
                        <Clock size={14} />
                        <span className="tabular-nums">
                          {getRemainingTime(
                            auction.closing_time,
                            auction.time_remaining_str,
                            auction.status,
                          )}
                        </span>
                      </div>
                      {auction.closing_time && (
                        <div className="closing-date">
                          Ends:{" "}
                          {new Date(auction.closing_time).toLocaleString(
                            "en-US",
                            {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                              hour12: true,
                            },
                          )}
                        </div>
                      )}
                    </div>
                    <div className="source-link">
                      <a href={auction.url} target="_blank" rel="noreferrer">
                        <Gavel size={14} />
                        {auction.website_name || "Generic Site"}
                        <ExternalLink size={12} className="ext" />
                      </a>
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      </main>

      <style jsx>{`
        .dashboard-root {
          min-height: 100vh;
          background-color: var(--bg-dark);
          color: var(--text-primary);
          position: relative;
          overflow-x: hidden;
        }

        .mesh-gradient {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background:
            radial-gradient(
              circle at 0% 0%,
              rgba(74, 122, 181, 0.05) 0%,
              transparent 50%
            ),
            radial-gradient(
              circle at 100% 100%,
              rgba(176, 141, 87, 0.05) 0%,
              transparent 50%
            );
          pointer-events: none;
          z-index: 0;
        }

        /* Nav Header */
        .premium-nav {
          position: sticky;
          top: 0;
          height: 80px;
          background: rgba(245, 242, 235, 0.8);
          backdrop-filter: blur(15px);
          border-bottom: 1px solid rgba(0, 0, 0, 0.05);
          z-index: 100;
          display: flex;
          align-items: center;
        }
        .nav-container {
          width: 100%;
          max-width: 1400px;
          margin: 0 auto;
          padding: 0 40px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .app-logo {
          display: flex;
          align-items: center;
          gap: 12px;
          color: var(--text-primary);
          font-weight: 800;
          letter-spacing: 1.5px;
          font-size: 18px;
        }
        .search-pill {
          background: rgba(0, 0, 0, 0.03);
          border: 1px solid rgba(0, 0, 0, 0.05);
          padding: 10px 20px;
          border-radius: 100px;
          display: flex;
          align-items: center;
          gap: 12px;
          width: 400px;
          transition: all 0.2s;
        }
        .search-pill:focus-within {
          background: white;
          box-shadow: 0 5px 15px rgba(0, 0, 0, 0.03);
          border-color: var(--accent-blue);
        }
        .search-pill input {
          background: none;
          border: none;
          outline: none;
          width: 100%;
          font-size: 14px;
        }
        .search-icon {
          color: var(--text-secondary);
        }

        .nav-right {
          display: flex;
          align-items: center;
          gap: 24px;
        }
        .user-info {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .avatar {
          width: 36px;
          height: 36px;
          background: var(--accent-blue);
          color: white;
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
        }
        .user-details {
          display: flex;
          flex-direction: column;
        }
        .email-label {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
        }
        .role-label {
          font-size: 11px;
          color: var(--text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .icon-btn {
          background: none;
          border: none;
          cursor: pointer;
          color: var(--text-secondary);
          padding: 8px;
          border-radius: 50%;
          transition: all 0.2s;
        }
        .icon-btn:hover {
          background: rgba(0, 0, 0, 0.05);
          color: #f43f5e;
        }

        /* Main Content */
        .main-content {
          position: relative;
          z-index: 10;
          padding: 40px;
        }
        .content-inner {
          max-width: 1400px;
          margin: 0 auto;
        }

        .dashboard-hero {
          margin-bottom: 50px;
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          gap: 40px;
        }
        .hero-text h1 {
          font-size: 36px;
          font-weight: 800;
          color: var(--text-primary);
          margin-bottom: 8px;
        }
        .hero-text p {
          color: var(--text-secondary);
          font-size: 16px;
        }

        .add-item-bar {
          display: flex;
          gap: 12px;
          background: white;
          padding: 8px;
          border-radius: 16px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.04);
          border: 1px solid rgba(0, 0, 0, 0.05);
          width: 100%;
          max-width: 600px;
        }
        .input-with-icon {
          flex: 1;
          display: flex;
          align-items: center;
          gap: 12px;
          padding-left: 12px;
        }
        .i-plus {
          color: var(--accent-blue);
        }
        .input-with-icon input {
          border: none;
          outline: none;
          width: 100%;
          font-size: 15px;
          background: none;
        }
        .submit-add {
          background: var(--text-primary);
          color: white;
          border: none;
          padding: 12px 24px;
          border-radius: 10px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.2s;
        }
        .submit-add:hover {
          transform: translateY(-2px);
          box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }

        .filter-shelf {
          display: flex;
          justify-content: space-between;
          margin-bottom: 30px;
        }
        .pill {
          background: white;
          border: 1px solid rgba(0, 0, 0, 0.05);
          padding: 8px 20px;
          border-radius: 100px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        .pill.active {
          background: var(--accent-blue);
          color: white;
          border-color: var(--accent-blue);
        }
        .pill.ghost {
          background: transparent;
          color: var(--text-secondary);
        }
        .filter-group,
        .sort-group {
          display: flex;
          gap: 8px;
        }

        /* Auction Cards Grid */
        .grid-container {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
          gap: 30px;
        }
        :global(.glass-card.auction-card) {
          background: rgba(255, 255, 255, 0.95);
          backdrop-filter: blur(20px) !important;
          -webkit-backdrop-filter: blur(20px) !important;
          border-radius: 32px !important;
          padding: 24px !important;
          /* Thick 4px White Border */
          border: 4px solid #ffffff !important;
          /* Strong contrast shadow to reveal the white border on light background */
          box-shadow:
            0 10px 30px rgba(0, 0, 0, 0.05),
            0 0 0 2px rgba(0, 0, 0, 0.03),
            /* Subtle outline for the white border */ inset 0 0 0 1px
              rgba(0, 0, 0, 0.02) !important;
          transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
          display: flex !important;
          flex-direction: column !important;
          gap: 20px !important;
          position: relative !important;
        }
        :global(.glass-card.auction-card:hover) {
          transform: translateY(-10px) !important;
          background: #ffffff !important;
          box-shadow:
            0 30px 60px rgba(0, 0, 0, 0.1),
            0 0 0 2px rgba(0, 0, 0, 0.05) !important;
          border-color: #ffffff !important;
          z-index: 50 !important;
        }

        :global(.glass-card.auction-card.expired) {
          background: rgba(255, 245, 245, 0.98) !important;
          border: 4px solid #ffdada !important;
          box-shadow:
            0 10px 30px rgba(220, 50, 50, 0.05),
            0 0 0 2px rgba(220, 50, 50, 0.05) !important;
        }
        :global(.glass-card.auction-card.expired:hover) {
          background: #fffafa !important;
          box-shadow: 0 30px 60px rgba(220, 50, 50, 0.1) !important;
          border-color: #ffcaca !important;
        }

        .card-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .status-indicator {
          display: flex;
          align-items: center;
          gap: 8px;
          background: rgba(0, 0, 0, 0.03);
          padding: 6px 12px;
          border-radius: 100px;
          font-size: 11px;
          font-weight: 800;
          text-transform: uppercase;
        }
        .dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }
        .dot.active {
          background: #10b981;
          box-shadow: 0 0 8px #10b981;
        }
        .dot.paused {
          background: #f59e0b;
        }
        .dot.expired {
          background: #94a3b8;
        }
        .dot.pending {
          background: #3b82f6;
        }
        .dot.fetching {
          background: #ef4444; /* Red dot */
          box-shadow: 0 0 10px #ef4444;
        }

        .card-actions {
          display: flex;
          gap: 8px;
        }
        .action-btn {
          width: 32px;
          height: 32px;
          border-radius: 8px;
          border: 1px solid rgba(0, 0, 0, 0.05);
          background: white;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          color: var(--text-secondary);
          transition: all 0.2s;
        }
        .action-btn:disabled {
          opacity: 0.3;
          cursor: not-allowed;
        }
        .action-btn:hover:not(:disabled) {
          color: var(--accent-blue);
          border-color: var(--accent-blue);
        }
        .action-btn.delete:hover:not(:disabled) {
          color: #f43f5e;
          border-color: #f43f5e;
        }
        .action-btn.btn-refresh {
          color: #4a7ab5;
          background: rgba(74, 122, 181, 0.05);
          border-color: rgba(74, 122, 181, 0.1);
        }
        .action-btn.btn-refresh:hover {
          background: rgba(74, 122, 181, 0.1);
          border-color: var(--accent-blue);
          color: var(--accent-blue);
        }

        .item-title {
          font-size: 16px;
          font-weight: 700;
          line-height: 1.4;
          margin-bottom: 12px;
          color: var(--text-primary);
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          min-height: 44px;
        }
        .meta-strip {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .meta-pill {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          color: var(--text-secondary);
          background: rgba(0, 0, 0, 0.03);
          padding: 4px 12px;
          border-radius: 100px;
          font-weight: 600;
          max-width: 180px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .stats-row {
          display: grid;
          grid-template-columns: 1fr 1.2fr;
          gap: 16px;
          background: #faf9f6;
          padding: 16px;
          border-radius: 20px;
        }
        .stat-box {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .stat-label {
          font-size: 9px;
          font-weight: 800;
          color: var(--text-secondary);
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .stat-value {
          font-size: 18px;
          font-weight: 800;
        }
        .stat-value.small {
          font-size: 14px;
          color: var(--text-secondary);
        }
        .stat-value.highlight {
          color: #10b981;
        }

        .card-bottom {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px;
          border-top: 1px dashed rgba(0, 0, 0, 0.08);
        }
        .time-group {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .time-left {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 14px;
          font-weight: 700;
          color: #f43f5e;
        }
        .closing-date {
          font-size: 10px;
          color: var(--text-secondary);
          font-weight: 600;
          opacity: 0.8;
          padding-left: 20px;
        }
        .source-link a {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: var(--accent-blue);
          text-decoration: none;
          font-weight: 600;
        }
        .ext {
          opacity: 0.5;
        }

        .icon-btn.sound {
          background: rgba(0, 0, 0, 0.03);
          border: 1.5px solid rgba(0, 0, 0, 0.05);
          color: var(--text-secondary);
          margin-right: 12px;
        }
        .icon-btn.sound.active {
          background: rgba(16, 185, 129, 0.1);
          border-color: rgba(16, 185, 129, 0.2);
          color: #10b981;
        }
        .icon-btn {
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .icon-btn:hover {
          transform: scale(1.05);
        }

        .icon-btn.refresh {
          background: rgba(0, 0, 0, 0.03);
          border: 1.5px solid rgba(0, 0, 0, 0.05);
          color: var(--accent-blue);
          margin-right: 4px;
        }

        .spinning {
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }

        .test-buzzer-btn {
          margin-top: 12px;
          font-size: 12px;
          opacity: 0.6;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .test-buzzer-btn:hover {
          opacity: 1;
        }

        .mega-tabs {
          display: flex;
          gap: 12px;
          margin-bottom: 24px;
          overflow-x: auto;
          padding-bottom: 8px;
          scrollbar-width: none; /* Firefox */
        }
        .mega-tabs::-webkit-scrollbar {
          display: none;
        } /* Chrome/Safari */

        .source-pill {
          padding: 10px 20px;
          border-radius: 14px;
          background: white;
          border: 1px solid var(--border-card);
          color: var(--text-secondary);
          font-weight: 700;
          font-size: 14px;
          white-space: nowrap;
          cursor: pointer;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
        }
        .source-pill:hover {
          background: #fdfdfd;
          transform: translateY(-1px);
          border-color: rgba(0, 0, 0, 0.1);
        }
        .source-pill.active {
          background: var(--accent-blue);
          color: white;
          border-color: var(--accent-blue);
          box-shadow: 0 10px 20px rgba(74, 122, 181, 0.25);
        }

        @media (max-width: 1024px) {
          .nav-center {
            display: none;
          }
          .grid-container {
            grid-template-columns: 1fr 1fr;
          }
        }
        @media (max-width: 768px) {
          .grid-container {
            grid-template-columns: 1fr;
          }
          .dashboard-hero {
            flex-direction: column;
            align-items: stretch;
          }
          .nav-container {
            padding: 0 20px;
          }
        }
      `}</style>
      <style jsx global>{`
        @keyframes pulse-red {
          from {
            opacity: 1;
            transform: scale(1);
          }
          to {
            opacity: 0.4;
            transform: scale(1.5);
          }
        }

        @keyframes blink-bg {
          0%,
          100% {
            background-color: rgba(255, 255, 255, 0.95);
          }
          50% {
            background-color: rgba(254, 243, 199, 0.85);
          }
        }

        @keyframes spin {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }

        .auction-card.is-fetching {
          border-color: #fbbf24 !important;
          animation: blink-bg 1.5s infinite ease-in-out !important;
          box-shadow: 0 0 20px rgba(251, 191, 36, 0.2) !important;
        }

        .auction-card.is-fetching .btn-refresh {
          animation: spin 1.5s linear infinite !important;
          background: rgba(74, 122, 181, 0.15) !important;
          border-color: var(--accent-blue) !important;
          color: var(--accent-blue) !important;
        }

        .dot.fetching {
          background: #ef4444 !important;
          box-shadow: 0 0 10px #ef4444 !important;
          animation: pulse-red 1s infinite alternate !important;
        }
      `}</style>
    </div>
  );
}
