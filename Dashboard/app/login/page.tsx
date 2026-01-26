'use client'

import { useState } from 'react'
import { createClient } from '@/utils/supabase-browser'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { Loader2, Eye, EyeOff } from 'lucide-react'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()
  const supabase = createClient()

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })

    if (error) {
      setError(error.message)
      setLoading(false)
    } else {
      router.push('/')
    }
  }

  return (
    <div className="login-wrapper">
      <div className="bg-image"></div>
      <div className="bg-overlay"></div>
      

      <div className="login-container">
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-card login-card"
        >
          <div className="login-header">
            <h1>LOGIN</h1>
          </div>

          <form onSubmit={handleLogin} className="login-form">
            <div className="input-group">
              <label>Email</label>
              <div className="input-with-icon">
                <input
                  type="email"
                  placeholder="name@example.com"
                  className="matte-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="input-group">
              <label>Password</label>
              <div className="input-with-icon">
                <input
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  className="matte-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="eye-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {error && <div className="error-message">{error}</div>}

            <button type="submit" disabled={loading} className="premium-login-submit">
              {loading ? <Loader2 className="animate-spin" /> : 'Login'}
            </button>

          </form>
        </motion.div>
      </div>

      <style jsx>{`
        .login-wrapper {
          position: relative;
          min-height: 100vh;
          width: 100vw;
          overflow: hidden;
          background: #000;
        }
        .bg-image {
          position: absolute;
          inset: 0;
          background-image: url("/login-bg.png");
          background-size: cover;
          background-position: center;
          filter: brightness(0.8);
        }
        .bg-overlay {
          position: absolute;
          inset: 0;
          background: radial-gradient(circle at center, transparent 0%, rgba(0,0,0,0.4) 100%);
        }
        

        .login-container {
          position: relative;
          z-index: 10;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          padding: 20px;
        }
        :global(.glass-card) {
          background: rgba(255, 255, 255, 0.1) !important;
          backdrop-filter: blur(40px) saturate(180%) !important;
          -webkit-backdrop-filter: blur(40px) saturate(180%) !important;
          border: 4px solid #ffffff !important; /* Thickest Solid White Border */
          box-shadow: 0 40px 100px rgba(0, 0, 0, 0.8) !important;
          z-index: 100;
        }
        :global(.login-card) {
          width: 100% !important;
          max-width: 500px !important;
          padding: 60px 50px !important;
          border-radius: 40px !important;
          margin: 0 auto !important;
        }
        .login-header h1 {
          color: white;
          font-size: 32px;
          font-weight: 700;
          text-align: center;
          margin-bottom: 40px;
          letter-spacing: 2px;
        }
        
        .login-form {
          display: flex;
          flex-direction: column;
          gap: 24px;
        }
        .input-group label {
          display: block;
          color: white;
          font-size: 15px;
          margin-bottom: 8px;
          font-weight: 500;
        }
        .input-with-icon {
          position: relative;
          display: flex;
          align-items: center;
        }
        .matte-input {
          width: 100%;
          background: none;
          border: none;
          border-bottom: 1px solid rgba(255,255,255,0.3);
          padding: 12px 0;
          color: white;
          font-size: 16px;
          outline: none;
          transition: border-color 0.3s;
        }
        .matte-input:focus {
          border-bottom-color: white;
        }
        .input-icon-right, .eye-toggle {
          position: absolute;
          right: 0;
          color: rgba(255,255,255,0.6);
        }
        .eye-toggle {
          background: none;
          border: none;
          cursor: pointer;
          padding: 0;
        }
        
        
        .premium-login-submit {
          height: 56px;
          background: linear-gradient(90deg, rgba(255,255,255,0.1), rgba(255,255,255,0.2));
          border: 1px solid rgba(255,255,255,0.2);
          border-radius: 8px;
          color: white;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.3s;
          margin-top: 12px;
          backdrop-filter: blur(5px);
        }
        .premium-login-submit:hover {
          background: rgba(255,255,255,0.25);
          border-color: rgba(255,255,255,0.4);
        }
        
        .register-text {
          text-align: center;
          color: white;
          font-size: 14px;
          margin-top: 10px;
          opacity: 0.9;
        }
        
        .error-message {
          color: #ff6b6b;
          background: rgba(255, 107, 107, 0.1);
          padding: 12px;
          border-radius: 8px;
          font-size: 14px;
          text-align: center;
        }
      `}</style>
    </div>
  )
}
