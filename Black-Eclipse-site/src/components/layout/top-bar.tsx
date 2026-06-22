'use client';

import { Sparkles, Sun, Moon, Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';

interface TopBarProps {
  isDark: boolean;
  onToggleTheme: () => void;
  onToggleMenu?: () => void;
}

export function TopBar({ isDark, onToggleTheme, onToggleMenu }: TopBarProps) {
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
         <Tooltip>
           <TooltipTrigger
             onClick={onToggleTheme}
             className="h-9 w-9 text-muted-foreground hover:text-foreground rounded-full hover:bg-accent flex items-center justify-center cursor-pointer outline-none"
           >
             {isDark ? <Sun size={18} className="md:size-[20px]" /> : <Moon size={18} className="md:size-[20px]" />}
           </TooltipTrigger>
           <TooltipContent>
             <p>{isDark ? 'Light Theme' : 'Dark Theme'}</p>
           </TooltipContent>
         </Tooltip>

         <Button 
           variant="secondary"
           size="sm"
           className="flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-1.5 rounded-full text-secondary-foreground text-xs md:text-sm font-medium border border-border"
         >
           <Sparkles size={12} className="text-primary md:size-[14px]" />
           Upgrade
         </Button>

         <div className="md:hidden ml-1">
            <div className="w-7 h-7 rounded-full bg-accent flex justify-center items-center font-semibold text-[10px] border border-border text-accent-foreground">
              AK
            </div>
         </div>
       </div>
    </div>
  );
}
