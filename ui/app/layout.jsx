"use client";

import "@/styles/globals.css";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { authHeader, clearRecruiterEmail } from "@/lib/user";
import { apiGet } from "@/lib/api";

const RUBRICS_KEY = "hiregraph_rubrics_uploaded";

export default function RootLayout({ children }) {
  const router   = useRouter();
  const pathname = usePathname();
  const [setupDone, setSetupDone] = useState(false);
  const [checking, setChecking]   = useState(true);
  const [recruiterName, setRecruiterName] = useState("");

  useEffect(() => {
    const verify = async () => {
      try {
        const { authenticated, name } = await apiGet("/auth/status");
        setSetupDone(authenticated);
        if (name) setRecruiterName(name);
        if (!authenticated && pathname !== "/setup") router.replace("/setup");
      } catch {
        if (pathname !== "/setup") router.replace("/setup");
      } finally {
        setChecking(false);
      }
    };
    verify();
  }, [pathname]);

  const handleLogout = async () => {
    try {
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/auth/logout`,
        { method: "DELETE", headers: { ...authHeader() } }
      );
    } catch {}
    clearRecruiterEmail();
    window.location.href = "/setup";
  };

  const onSetupPage = pathname === "/setup";
  const navItems = [
    { href: "/",          label: "Pipelines"       },
    { href: "/knowledge", label: "Knowledge Base"  },
  ];

  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>HireGraph | AI Recruiting</title>
        <meta name="description" content="AI-powered recruiting pipeline with human-in-the-loop reviews" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      </head>
      <body>
        <header className="header">
          <div className="header-content">
            <Link href={setupDone ? "/" : "/setup"} className="logo">
              HireGraph
            </Link>

            {setupDone && (
              <nav className="nav-links">
                {navItems.map(item => (
                  <Link
                    key={item.href}
                    href={item.href}
                    style={{
                      color: pathname === item.href ? "var(--gray-900)" : undefined,
                      background: pathname === item.href ? "var(--gray-100)" : undefined,
                    }}
                  >
                    {item.label}
                  </Link>
                ))}

                <div style={{ width: "1px", height: "20px", background: "var(--border)", margin: "0 0.5rem" }} />

                {recruiterName && (
                  <span style={{ fontSize: "0.8rem", color: "var(--gray-500)", fontWeight: 500 }}>
                    {recruiterName}
                  </span>
                )}

                <button
                  onClick={handleLogout}
                  style={{
                    fontSize: "0.8rem", fontWeight: 600,
                    color: "var(--gray-500)", padding: "0.35rem 0.75rem",
                    border: "1px solid var(--border)", borderRadius: "var(--radius)",
                    background: "var(--surface)", cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={e => { e.target.style.color = "var(--gray-800)"; e.target.style.borderColor = "var(--gray-300)"; }}
                  onMouseLeave={e => { e.target.style.color = "var(--gray-500)"; e.target.style.borderColor = "var(--border)"; }}
                >
                  Sign out
                </button>
              </nav>
            )}
          </div>
        </header>

        <main className="main-content">
          <div className="container">
            {checking && !onSetupPage ? (
              <div style={{ textAlign: "center", padding: "5rem" }}>
                <div className="loading" style={{ width: 28, height: 28, margin: "0 auto" }} />
              </div>
            ) : (
              <div className="fade-up">{children}</div>
            )}
          </div>
        </main>

        <footer style={{
          textAlign: "center", padding: "1.5rem",
          color: "var(--gray-400)", fontSize: "0.78rem",
          borderTop: "1px solid var(--border-light)",
        }}>
          HireGraph © {new Date().getFullYear()} - AI Recruiting Pipeline
        </footer>
      </body>
    </html>
  );
}
