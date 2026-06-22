"use client";

import React, { useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { 
  LayoutDashboard, FileText, Star, Settings, 
  Sparkles, ShieldAlert, Compass, ChevronLeft, ChevronRight, LogOut 
} from "lucide-react";
import { useAuth } from "@/components/auth/auth-context";

export function DashboardSidebar({ isAdmin }: { isAdmin: boolean }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const { user, logout } = useAuth();

  const navItems = [
    { href: "/dashboard", icon: ShieldAlert, label: "JDdS Control Panel" },
    { href: "/dashboard/reports", icon: FileText, label: "Reports" },
    { href: "/dashboard/watchlists", icon: Star, label: "Watchlists" },
    { href: "/", icon: Compass, label: "Open Research Site" },
  ];

  return (
    <>
      {/* Slideable Sidebar */}
      <aside 
        className={`fixed left-0 top-0 z-30 flex h-full flex-col bg-card/85 backdrop-blur-3xl border-r border-border/60 select-none text-foreground font-sans transition-all duration-300 group/sidebar ${
          collapsed ? "w-16 px-0 items-center" : "w-60 px-4"
        }`}
      >
        {/* Brand logo header */}
        <div className={`flex h-14 md:h-16 items-center shrink-0 relative w-full ${
          collapsed ? "justify-center" : "justify-between gap-2 px-1"
        }`}>
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="relative w-8 h-8 flex items-center justify-center shrink-0">
              {/* Sparkles Logo (hidden on hover when collapsed) */}
              <div className={`w-8 h-8 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center text-primary-foreground shadow-sm shadow-primary/20 transition-all duration-200 ${
                collapsed ? "group-hover/sidebar:opacity-0 group-hover/sidebar:scale-75" : ""
              }`}>
                <Sparkles size={14} className="animate-pulse" />
              </div>
              
              {/* Expand Slide Icon (shows on hover when collapsed instead of logo/icon) */}
              {collapsed && (
                <button
                  onClick={() => setCollapsed(false)}
                  className="absolute inset-0 flex items-center justify-center rounded-xl border border-border/40 bg-card text-muted-foreground hover:text-foreground cursor-pointer shadow opacity-0 scale-75 group-hover/sidebar:opacity-100 group-hover/sidebar:scale-100 transition-all duration-200 hover:bg-accent"
                  title="Expand Sidebar"
                >
                  <ChevronRight size={14} />
                </button>
              )}
            </div>
            {!collapsed && (
              <span className="text-sm font-semibold tracking-tight truncate font-sans text-white">
                BlackEclipse
              </span>
            )}
          </div>

          {/* Collapse button on the right of logo when expanded (only visible on hover) */}
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              className="rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer opacity-0 group-hover/sidebar:opacity-100 transition-opacity duration-200"
              title="Collapse Sidebar"
            >
              <ChevronLeft size={16} />
            </button>
          )}
        </div>

        {/* Navigation Section (divider line on top of icons) */}
        <nav className={`flex-1 flex flex-col gap-1.5 py-4 overflow-y-auto scrollbar-hide border-t border-border/10 w-full ${
          collapsed ? "items-center" : ""
        }`}>
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;

            if (collapsed) {
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all border border-transparent cursor-pointer mx-auto ${
                    isActive
                      ? "text-primary bg-primary/10 border-primary/20 scale-105"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
                  }`}
                  title={item.label}
                >
                  <Icon size={16} />
                </Link>
              );
            }

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-xs font-semibold transition-all cursor-pointer border border-transparent ${
                  isActive
                    ? "bg-primary/15 text-foreground shadow-sm shadow-primary/5 font-bold"
                    : "bg-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground"
                }`}
              >
                <Icon size={16} className={isActive ? "text-primary" : ""} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Footer / Account Section */}
        <div className={`border-t border-border/10 py-4 shrink-0 flex flex-col gap-2 w-full ${
          collapsed ? "items-center" : ""
        }`}>
          {/* Settings Nav Item */}
          {collapsed ? (
            <Link
              href="/dashboard/settings"
              className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all border border-transparent cursor-pointer mx-auto ${
                pathname === "/dashboard/settings"
                  ? "text-primary bg-primary/10 border-primary/20 scale-105"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
              }`}
              title="Settings"
            >
              <Settings size={16} />
            </Link>
          ) : (
            <Link
              href="/dashboard/settings"
              className={`flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-xs font-semibold transition-all border cursor-pointer ${
                pathname === "/dashboard/settings"
                  ? "bg-primary/15 border-primary/30 text-foreground shadow-sm shadow-primary/5"
                  : "bg-transparent border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground"
              }`}
            >
              <Settings size={16} className={pathname === "/dashboard/settings" ? "text-primary" : ""} />
              <span>Settings</span>
            </Link>
          )}

          {/* User Account / Logout */}
          {collapsed ? (
            <div className="flex justify-center">
              {user ? (
                <button
                  onClick={() => logout()}
                  className="w-9 h-9 rounded-xl bg-destructive/10 text-destructive border border-destructive/20 flex justify-center items-center font-bold text-xs cursor-pointer hover:bg-destructive hover:text-destructive-foreground transition-all"
                  title={`Sign Out (${user.name || user.email})`}
                >
                  <LogOut size={14} />
                </button>
              ) : (
                <div className="w-9 h-9 rounded-xl bg-accent border border-border flex justify-center items-center font-bold text-xs text-muted-foreground">
                  G
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-between px-1 text-[11px]">
              <div className="flex flex-col truncate max-w-[130px]">
                <span className="font-semibold text-foreground truncate">{user ? (user.name || user.email) : "Guest Mode"}</span>
                <span className="text-[9px] text-muted-foreground uppercase">{user ? user.role : "Read-Only"}</span>
              </div>
              {user && (
                <button
                  onClick={() => logout()}
                  className="p-1.5 rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-rose-400 cursor-pointer"
                  title="Logout"
                >
                  <LogOut size={14} />
                </button>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* Spacer to push content area appropriately */}
      <div 
        className={`hidden md:block transition-all duration-300 shrink-0 ${
          collapsed ? "w-16" : "w-60"
        }`} 
      />
    </>
  );
}
