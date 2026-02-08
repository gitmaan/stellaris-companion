import React, { ReactNode } from 'react';

interface HUDContainerProps {
  children: ReactNode;
  className?: string;
}

export const HUDContainer: React.FC<HUDContainerProps> = ({ children, className = '' }) => {
  return (
    <div className={`relative w-full h-screen overflow-hidden bg-bg-primary text-text-primary ${className}`}>
      {/* Background Layers */}
      
      {/* 1. Deep Space Base Gradient */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_#0c1219_0%,_#000000_100%)] z-0" />
      
      {/* 2. Stars / Nebula subtle effect (CSS generated) */}
      <div className="absolute inset-0 opacity-30 z-0 bg-[url('https://www.transparenttextures.com/patterns/stardust.png')] mix-blend-screen" />
      
      {/* 3. Grid Overlay (The "Floor" or tactical map feel) */}
      <div className="absolute inset-0 bg-grid-pattern bg-grid opacity-20 [mask-image:linear-gradient(to_bottom,transparent,black)] z-0 pointer-events-none" />

      {/* 4. Vignette for focus */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_50%,rgba(0,0,0,0.8)_100%)] z-10 pointer-events-none" />

      {/* 5. Scanline Effect */}
      <div className="absolute inset-0 bg-scanline opacity-10 pointer-events-none z-50" />
      
      {/* 6. Decorative Corner HUD Elements (Fixed to screen) */}
      <div className="absolute top-4 left-4 w-32 h-32 border-l border-t border-border-glow opacity-50 z-20 pointer-events-none hud-corner-top" />
      <div className="absolute top-4 right-4 w-32 h-32 border-r border-t border-border-glow opacity-50 z-20 pointer-events-none hud-corner-top" />
      <div className="absolute bottom-4 left-4 w-32 h-32 border-l border-b border-border-glow opacity-50 z-20 pointer-events-none" />
      <div className="absolute bottom-4 right-4 w-32 h-32 border-r border-b border-border-glow opacity-50 z-20 pointer-events-none" />

      {/* Content Layer */}
      <div className="relative z-30 h-full w-full overflow-hidden flex flex-col">
        {children}
      </div>
    </div>
  );
};
