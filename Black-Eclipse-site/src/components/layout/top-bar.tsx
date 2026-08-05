'use client';

import { Sparkles, Menu } from 'lucide-react';

interface TopBarProps {
  onToggleMenu?: () => void;
}

export function TopBar({ onToggleMenu }: TopBarProps) {
  return (
    <div className="w-full h-14 md:h-16 flex items-center justify-between px-4 md:px-6 gap-2 md:gap-4 z-20 shrink-0">
       {/* Mobile Logo & Menu Toggle */}
       <div className="flex items-center gap-2">
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
       
       <div className="flex items-center gap-2 md:gap-4">
         <div className="md:hidden ml-1">
            <div className="w-7 h-7 rounded-full bg-accent flex justify-center items-center font-semibold text-[10px] border border-border text-accent-foreground">
              AK
            </div>
         </div>
       </div>
    </div>
  );
}
