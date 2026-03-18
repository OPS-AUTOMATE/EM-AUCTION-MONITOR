# Security Policy

## 🛡 Security Overview
Eighteen Medical is committed to ensuring the safety and integrity of our automated systems and our users' data. This document outlines our policy for reporting security vulnerabilities.

## 🚨 Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability in the Auction Monitor Bot or Dashboard, please report it privately to our development team.

### Preferred Method
Please send an email to **ar.abdul.dev@gmail.com** with the following information:
1.  **Description**: A detailed description of the vulnerability.
2.  **Impact**: What is the potential risk?
3.  **Reproduction**: Steps to reproduce the issue (screenshots or code snippets are helpful).
4.  **Version**: The version or commit hash where the issue was found.

## ✅ Scope
- **Critical**: Database breaches, unauthorized administrative access, or credential exposure.
- **High**: CSRF/XSS on the dashboard, bypass of URL validation, or session hijacking.
- **Medium**: Denial of Service (DoS) risks, information disclosure.

## 🚫 Out of Scope
- Brute-force attacks (monitored by Supabase).
- Social engineering attacks.
- Denial of Service (DDoS) against the host auction platforms (we use rate limiting).

## 🕒 Response Timeline
- **Acknowledgement**: Within 24 hours.
- **Initial Analysis**: Within 3 business days.
- **Resolution**: Aimed at within 14 business days.

## 🔐 Best Practices for Users
- **Credentials**: Never commit your browser session files or `.env` files to version control.
- **Environment**: Always run the bot in a secure, isolated environment (VPS or Docker).
- **Updates**: Keep the dashboard dependencies updated to the latest stable versions to mitigate Next.js and React security risks.

Thank you for helping us keep this system secure!
