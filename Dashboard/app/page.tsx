'use client'

import { useEffect, useState, useCallback } from 'react'
import { createClient } from '@/utils/supabase-browser'
import { useRouter } from 'next/navigation'
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
  Users
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface User {
  id: string
  email?: string
}

interface Auction {
  id: string
  item_name?: string
  current_bid?: number
  premium_percentage?: number
  total_bidders?: number
  time_remaining_str?: string
  city?: string
  state?: string
  serial_number?: string
  website_name?: string
  url: string
  closing_time?: string
  status: 'active' | 'paused' | 'pending' | 'error' | 'expired'
}

interface RealtimeUpdatePayload {
  eventType: 'INSERT' | 'UPDATE' | 'DELETE'
  new: Auction
  old: { id: string }
}

export default function Dashboard() {
  const [user, setUser] = useState<User | null>(null)
  const [auctions, setAuctions] = useState<Auction[]>([])
  const [newUrl, setNewUrl] = useState('')
  const [addingItem, setAddingItem] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | 'active' | 'ended'>('all')
  const router = useRouter()
  const supabase = createClient()

  const fetchAuctions = useCallback(async (userId: string) => {
    const { data } = await supabase
      .from('auctions')
      .select('*')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
    
    if (data) setAuctions(data as Auction[])
  }, [supabase])

  const handleRealtimeUpdate = useCallback((payload: RealtimeUpdatePayload) => {
    const { eventType, new: newRecord, old: oldRecord } = payload
    if (eventType === 'INSERT') {
      setAuctions(prev => [newRecord, ...prev])
    } else if (eventType === 'UPDATE') {
      setAuctions(prev => prev.map(a => a.id === newRecord.id ? newRecord : a))
    } else if (eventType === 'DELETE') {
      setAuctions(prev => prev.filter(a => a.id === oldRecord.id))
    }
  }, [])

  const [tick, setTick] = useState(0) // eslint-disable-line @typescript-eslint/no-unused-vars

  useEffect(() => {
    // Tick is used to trigger re-renders for the live countdown
    const timer = setInterval(() => setTick(prev => prev + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  const getRemainingTime = (closingTime: string | undefined, staticStr: string | undefined) => {
    if (!closingTime) return staticStr || 'Syncing...'
    
    const end = new Date(closingTime).getTime()
    const now = new Date().getTime()
    const diff = end - now
    
    if (diff <= 0) return 'Ended'
    
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
    const seconds = Math.floor((diff % (1000 * 60)) / 1000)
    
    const parts = []
    if (days > 0) parts.push(`${days}d`)
    if (hours > 0 || days > 0) parts.push(`${hours}h`)
    if (minutes > 0 || hours > 0 || days > 0) parts.push(`${minutes}m`)
    parts.push(`${seconds}s`)
    
    return parts.join(' ')
  }

  useEffect(() => {
    const checkUser = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        router.push('/login')
      } else {
        setUser(session.user as User)
        fetchAuctions(session.user.id)
      }
    }
    checkUser()

    const channel = supabase
      .channel('dashboard-sync')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'auctions' },
        (payload) => {
          handleRealtimeUpdate(payload as unknown as RealtimeUpdatePayload)
        }
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [router, supabase, fetchAuctions, handleRealtimeUpdate])

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newUrl || !user) return

    // Duplicate Prevention Check
    const isDuplicate = auctions.some(a => 
      a.url.toLowerCase().trim().replace(/\/$/, "") === newUrl.toLowerCase().trim().replace(/\/$/, "")
    )

    if (isDuplicate) {
      alert('This URL is already being monitored!')
      setNewUrl('')
      return
    }

    setAddingItem(true)

    const { error } = await supabase
      .from('auctions')
      .insert([
        { 
          url: newUrl, 
          user_id: user.id,
          status: 'active'
        }
      ])

    if (!error) {
      setNewUrl('')
    } else {
      console.error('Add item error:', error)
      alert('Failed to add URL. Please try again.')
    }
    setAddingItem(false)
  }

  const handleLogout = async () => {
    await supabase.auth.signOut()
    router.push('/login')
  }

  const handleDelete = async (id: string) => {
    console.log('Attempting to delete item:', id);
    const { error } = await supabase.from('auctions').delete().eq('id', id)
    if (error) console.error('Delete error:', error)
    else setAuctions(prev => prev.filter(a => a.id !== id))
  }

  const toggleStatus = async (id: string, currentStatus: string) => {
    const newStatus = currentStatus === 'active' ? 'paused' : 'active'
    console.log(`Toggling status for ${id}: ${currentStatus} -> ${newStatus}`);
    const { error } = await supabase.from('auctions').update({ status: newStatus }).eq('id', id)
    if (error) console.error('Toggle status error:', error)
    else setAuctions(prev => prev.map(a => a.id === id ? { ...a, status: newStatus as Auction['status'] } : a))
  }

  const filteredAuctions = auctions
    .filter(a => {
      // 1. Search Filter (Safe for undefined names)
      const matchesSearch = 
        (a.item_name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? true) || 
        (a.website_name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? true) ||
        searchQuery === ''

      // 2. Tab Filter
      const matchesTab = 
        activeTab === 'all' || 
        (activeTab === 'active' && a.status === 'active') ||
        (activeTab === 'ended' && a.status === 'expired')

      return matchesSearch && matchesTab
    })
    .sort((a, b) => {
      // Sort by closing_time (soonest first)
      if (!a.closing_time) return 1
      if (!b.closing_time) return -1
      return new Date(a.closing_time).getTime() - new Date(b.closing_time).getTime()
    })

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
            <div className="user-info">
              <div className="avatar">
                {user?.email?.[0].toUpperCase()}
              </div>
              <div className="user-details">
                <span className="email-label">{user?.email}</span>
                <span className="role-label">Procurement Admin</span>
              </div>
            </div>
            <button onClick={handleLogout} className="icon-btn logout" title="Sign Out">
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
              <p>Tracking {auctions.length} medical equipment listings across 15+ websites.</p>
            </div>
            
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
                {addingItem ? <RefreshCw className="animate-spin" size={18} /> : 'Track Link'}
              </button>
            </form>
          </section>

          {/* Quick Filters */}
          <div className="filter-shelf">
            <div className="filter-group">
              <button 
                onClick={() => setActiveTab('all')}
                className={`pill ${activeTab === 'all' ? 'active' : ''}`}
              >
                All Items
              </button>
              <button 
                onClick={() => setActiveTab('active')}
                className={`pill ${activeTab === 'active' ? 'active' : ''}`}
              >
                Active
              </button>
              <button 
                onClick={() => setActiveTab('ended')}
                className={`pill ${activeTab === 'ended' ? 'active' : ''}`}
              >
                Ended
              </button>
            </div>
            <div className="sort-group">
              <button className="pill ghost"><ArrowUpDown size={14} /> Time Remaining</button>
              <button className="pill ghost"><Filter size={14} /> Filters</button>
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
                  className={`glass-card auction-card ${auction.status}`}
                >
                  <div className="card-top">
                    <div className="status-indicator">
                      <div className={`dot ${auction.status}`}></div>
                      <span>{auction.status}</span>
                    </div>
                    <div className="card-actions">
                      <button 
                        onClick={() => toggleStatus(auction.id, auction.status)}
                        className="action-btn" 
                        title={auction.status === 'active' ? 'Pause' : 'Resume'}
                        disabled={auction.status === 'expired'}
                      >
                        {auction.status === 'active' ? <Pause size={16} /> : <Play size={16} />}
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
                    <h2 className="item-title">{auction.item_name || 'Processing URL...'}</h2>
                    <div className="meta-strip">
                      <div className="meta-pill">
                        <MapPin size={12} />
                        <span>{auction.city ? `${auction.city}, ${auction.state}` : 'Locating...'}</span>
                      </div>
                      <div className="meta-pill">
                        <Users size={12} />
                        <span>{auction.total_bidders || 0} Bidders</span>
                      </div>
                    </div>
                  </div>

                  <div className="stats-row">
                    <div className="stat-box">
                      <div className="stat-label">
                        <TrendingUp size={14} />
                        BID + {auction.premium_percentage || 0}%
                      </div>
                      <div className="stat-value small">
                        ${auction.current_bid?.toLocaleString() || '0.00'}
                      </div>
                    </div>
                    <div className="stat-box">
                      <div className="stat-label">
                        TOTAL PRICE
                      </div>
                      <div className="stat-value highlight">
                        ${((auction.current_bid || 0) * (1 + (auction.premium_percentage || 0) / 100)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </div>
                    </div>
                  </div>

                  <div className="card-bottom">
                    <div className="time-group">
                      <div className="time-left">
                        <Clock size={14} />
                        <span className="tabular-nums">
                          {getRemainingTime(auction.closing_time, auction.time_remaining_str)}
                        </span>
                      </div>
                      {auction.closing_time && (
                        <div className="closing-date">
                           Ends: {new Date(auction.closing_time).toLocaleString('en-US', {
                               month: 'short',
                               day: 'numeric',
                               year: 'numeric',
                               hour: 'numeric',
                               minute: '2-digit',
                               hour12: true
                           })}
                        </div>
                      )}
                    </div>
                    <div className="source-link">
                      <a href={auction.url} target="_blank" rel="noreferrer">
                        <Gavel size={14} />
                        {auction.website_name || 'Generic Site'}
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
            radial-gradient(circle at 0% 0%, rgba(74, 122, 181, 0.05) 0%, transparent 50%),
            radial-gradient(circle at 100% 100%, rgba(176, 141, 87, 0.05) 0%, transparent 50%);
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
          border-bottom: 1px solid rgba(0,0,0,0.05);
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
          background: rgba(0,0,0,0.03);
          border: 1px solid rgba(0,0,0,0.05);
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
          box-shadow: 0 5px 15px rgba(0,0,0,0.03);
          border-color: var(--accent-blue);
        }
        .search-pill input {
          background: none;
          border: none;
          outline: none;
          width: 100%;
          font-size: 14px;
        }
        .search-icon { color: var(--text-secondary); }

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
        .email-label { font-size: 14px; font-weight: 600; color: var(--text-primary); }
        .role-label { font-size: 11px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
        .icon-btn {
          background: none;
          border: none;
          cursor: pointer;
          color: var(--text-secondary);
          padding: 8px;
          border-radius: 50%;
          transition: all 0.2s;
        }
        .icon-btn:hover { background: rgba(0,0,0,0.05); color: #f43f5e; }

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
        .hero-text h1 { font-size: 36px; font-weight: 800; color: var(--text-primary); margin-bottom: 8px; }
        .hero-text p { color: var(--text-secondary); font-size: 16px; }

        .add-item-bar {
          display: flex;
          gap: 12px;
          background: white;
          padding: 8px;
          border-radius: 16px;
          box-shadow: 0 10px 30px rgba(0,0,0,0.04);
          border: 1px solid rgba(0,0,0,0.05);
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
        .i-plus { color: var(--accent-blue); }
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
        .submit-add:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }

        .filter-shelf {
          display: flex;
          justify-content: space-between;
          margin-bottom: 30px;
        }
        .pill {
          background: white;
          border: 1px solid rgba(0,0,0,0.05);
          padding: 8px 20px;
          border-radius: 100px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        .pill.active { background: var(--accent-blue); color: white; border-color: var(--accent-blue); }
        .pill.ghost { background: transparent; color: var(--text-secondary); }
        .filter-group, .sort-group { display: flex; gap: 8px; }

        /* Auction Cards Grid */
        .grid-container {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
          gap: 30px;
        }
        :global(.glass-card.auction-card) {
          background: rgba(255, 255, 255, 0.95) !important;
          backdrop-filter: blur(20px) !important;
          -webkit-backdrop-filter: blur(20px) !important;
          border-radius: 32px !important;
          padding: 24px !important;
          /* Thick 4px White Border */
          border: 4px solid #ffffff !important;
          /* Strong contrast shadow to reveal the white border on light background */
          box-shadow: 
            0 10px 30px rgba(0, 0, 0, 0.05),
            0 0 0 2px rgba(0, 0, 0, 0.03), /* Subtle outline for the white border */
            inset 0 0 0 1px rgba(0, 0, 0, 0.02) !important;
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
          background: rgba(0,0,0,0.03);
          padding: 6px 12px;
          border-radius: 100px;
          font-size: 11px;
          font-weight: 800;
          text-transform: uppercase;
        }
        .dot { width: 6px; height: 6px; border-radius: 50%; }
        .dot.active { background: #10b981; box-shadow: 0 0 8px #10b981; }
        .dot.paused { background: #f59e0b; }
        .dot.expired { background: #94a3b8; }
        .dot.pending { background: #3b82f6; }

        .card-actions { display: flex; gap: 8px; }
        .action-btn {
          width: 32px;
          height: 32px;
          border-radius: 8px;
          border: 1px solid rgba(0,0,0,0.05);
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
        .action-btn:hover:not(:disabled) { color: var(--accent-blue); border-color: var(--accent-blue); }
        .action-btn.delete:hover:not(:disabled) { color: #f43f5e; border-color: #f43f5e; }

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
          background: rgba(0,0,0,0.03);
          padding: 4px 10px;
          border-radius: 100px;
          font-weight: 600;
        }

        .stats-row {
          display: grid;
          grid-template-columns: 1fr 1.2fr;
          gap: 16px;
          background: #faf9f6;
          padding: 16px;
          border-radius: 20px;
        }
        .stat-box { display: flex; flex-direction: column; gap: 4px; }
        .stat-label { font-size: 9px; font-weight: 800; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
        .stat-value { font-size: 18px; font-weight: 800; }
        .stat-value.small { font-size: 14px; color: var(--text-secondary); }
        .stat-value.highlight { color: #10b981; }

        .card-bottom {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px;
          border-top: 1px dashed rgba(0,0,0,0.08);
        }
        .time-group { display: flex; flex-direction: column; gap: 4px; }
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
        .ext { opacity: 0.5; }

        @media (max-width: 1024px) {
          .nav-center { display: none; }
          .grid-container { grid-template-columns: 1fr 1fr; }
        }
        @media (max-width: 768px) {
          .grid-container { grid-template-columns: 1fr; }
          .dashboard-hero { flex-direction: column; align-items: stretch; }
          .nav-container { padding: 0 20px; }
        }
      `}</style>
    </div>
  )
}
