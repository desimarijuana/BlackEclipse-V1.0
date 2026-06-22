'use client';

import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

export function TopLoader() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  if (!mounted) return null;

  return createPortal(
    <div className="fixed top-0 left-0 w-full h-[3px] bg-white/5 z-[9999] overflow-hidden">
      <div 
        className="h-full bg-gradient-to-r from-[#7aff78] via-[#047857] to-[#7aff78] w-full animate-loading-bar"
        style={{
          transformOrigin: '0% 50%',
        }}
      />
    </div>,
    document.body
  );
}
