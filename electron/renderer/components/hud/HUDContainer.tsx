import React, { HTMLAttributes, ReactNode } from 'react';

interface HUDContainerProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export const HUDContainer: React.FC<HUDContainerProps> = ({ children, className = '', ...props }) => {
  return (
    <div
      className={`relative w-full h-screen overflow-hidden bg-bg-primary text-text-primary ${className}`}
      {...props}
    >
      {/* Background Layers */}
      
      {/* 1. Deep Space Base Gradient */}
      <div
        className="absolute inset-0 z-0"
        style={{
          background: 'radial-gradient(circle at center, rgb(var(--color-bg-secondary) / 1) 0%, rgb(var(--color-bg-primary) / 1) 100%)',
        }}
      />
      
      {/* 2. Stars / Nebula subtle effect (CSS generated) */}
      <div
        className="absolute inset-0 z-0 bg-[url('https://www.transparenttextures.com/patterns/stardust.png')] mix-blend-screen"
        style={{ opacity: 'var(--theme-stars-opacity, 0.3)' }}
      />
      
      {/* 3. Grid Overlay (The "Floor" or tactical map feel) */}
      <div
        className="absolute inset-0 bg-grid-pattern bg-grid [mask-image:linear-gradient(to_bottom,transparent,black)] z-0 pointer-events-none"
        style={{ opacity: 'var(--theme-grid-opacity, 0.2)' }}
      />

      {/* 4. Vignette for focus */}
      <div
        className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background: 'radial-gradient(circle at center, transparent 50%, rgb(0 0 0 / var(--theme-vignette-alpha, 0.8)) 100%)',
        }}
      />

      {/* 5. Scanline Effect */}
      <div
        className="absolute inset-0 bg-scanline pointer-events-none z-50"
        style={{ opacity: 'var(--theme-hud-scanline-opacity, 0.1)' }}
      />
      
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
