'use client';

import { Sparkles, Menu, Search, Command } from 'lucide-react';
import { useCommandStore } from '@/lib/search/store';

interface TopBarProps {
  onToggleMenu?: () => void;
}

export function TopBar({ onToggleMenu }: TopBarProps) {
  return (
    <div className="w-full h-14 md:h-16 flex items-center justify-between px-3 md:px-6 gap-2 md:gap-4 z-20 shrink-0">
       {/* Mobile Logo & Menu Toggle */}
       <div className="flex items-center gap-2 shrink-0">
         {onToggleMenu && (
           <button
             onClick={onToggleMenu}
             className="md:hidden p-1.5 text-muted-foreground hover:text-foreground rounded-xl hover:bg-accent cursor-pointer transition-colors"
           >
             <Menu size={20} />
           </button>
         )}
         <div className="flex md:hidden items-center gap-2 text-primary font-medium">
           <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-primary-foreground shadow-sm shadow-primary/20">
             <Sparkles size={14} />
           </div>
           <span className="text-foreground text-xs font-mono font-bold tracking-tight">BlackEclipse</span>
         </div>
       </div>

       {/* Right-aligned, medium frosted-glass search bar */}
       <div className="flex-1 flex justify-end min-w-0 px-2">
          <button
            onClick={() => useCommandStore.getState().setOpen(true)}
            className="command-glass-bar group flex w-full max-w-md items-center gap-2.5 rounded-xl px-4 py-2.5 transition-all cursor-pointer text-left"
            title="Search & command center (⌘K)"
          >
            <Search size={16} className="text-muted-foreground/70 shrink-0 transition-colors group-hover:text-primary" />
            <span className="flex-1 truncate text-sm text-muted-foreground/80 font-mono">
              Search instruments, indicators, commands…
            </span>
            <kbd className="hidden sm:inline-flex items-center gap-1 rounded-md bg-white/[0.05] px-2 py-0.5 text-[11px] font-mono text-muted-foreground">
              <Command size={11} /> K
            </kbd>
          </button>
       </div>
    </div>
  );
}
