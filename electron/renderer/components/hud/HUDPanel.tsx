import React, { ReactNode } from 'react';

interface HUDPanelProps {
  children: ReactNode;
  title?: string;
  className?: string;
  variant?: 'primary' | 'secondary' | 'alert' | 'glass';
  decoration?: 'none' | 'brackets' | 'tech' | 'scanline';
  noPadding?: boolean;
}

export const HUDPanel: React.FC<HUDPanelProps> = ({ 
  children, 
  title, 
  className = '', 
  variant = 'primary',
  decoration = 'none',
  noPadding = false 
}) => {
  const baseClasses = "relative rounded-sm overflow-hidden backdrop-blur-md transition-all duration-300";
  
  const variantClasses = {
    primary: "bg-bg-glass border border-border-subtle hover:border-accent-cyan/30",
    secondary: "bg-bg-tertiary/40 border border-white/5",
    alert: "bg-accent-red/10 border border-accent-red/30 shadow-[0_0_15px_rgba(252,129,129,0.1)]",
    glass: "bg-black/20 border border-white/5 shadow-glass",
  };

  // Border override for 'brackets' style - we remove the full border
  const finalVariantClass = decoration === 'brackets' 
    ? variantClasses[variant].replace('border border-border-subtle', '').replace('border border-white/5', '') 
    : variantClasses[variant];

  return (
    <div className={`${baseClasses} ${finalVariantClass} ${className}`}>
      
      {/* Decoration: Brackets (Corners only) */}
      {(decoration === 'brackets' || variant === 'primary') && (
        <>
          <div className="absolute top-0 left-0 w-3 h-3 border-l-2 border-t-2 border-accent-cyan opacity-70 pointer-events-none" />
          <div className="absolute top-0 right-0 w-3 h-3 border-r-2 border-t-2 border-accent-cyan opacity-70 pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-3 h-3 border-l-2 border-b-2 border-accent-cyan opacity-70 pointer-events-none" />
          <div className="absolute bottom-0 right-0 w-3 h-3 border-r-2 border-b-2 border-accent-cyan opacity-70 pointer-events-none" />
        </>
      )}

      {/* Decoration: Tech (Header bar with ticks) */}
      {decoration === 'tech' && (
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-accent-cyan/50 to-transparent opacity-50 pointer-events-none">
           <div className="absolute top-0 left-1/4 w-px h-2 bg-accent-cyan" />
           <div className="absolute top-0 right-1/4 w-px h-2 bg-accent-cyan" />
        </div>
      )}

      {/* Decoration: Scanline Animation */}
      {decoration === 'scanline' && (
        <div className="absolute inset-0 bg-scanline opacity-5 pointer-events-none z-0" />
      )}

      {title && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-white/5 relative z-10">
          <h3 className="font-display text-xs tracking-tech text-accent-cyan uppercase drop-shadow-[0_0_5px_rgba(0,212,255,0.5)]">
            {title}
          </h3>
          {/* Decorative lines next to title */}
          <div className="h-px flex-1 bg-gradient-to-r from-accent-cyan/20 to-transparent ml-4 relative">
             <div className="absolute right-0 top-1/2 -translate-y-1/2 w-1 h-1 bg-accent-cyan/50 rounded-full" />
          </div>
        </div>
      )}

      <div className={`relative z-10 ${noPadding ? '' : 'p-4'}`}>
        {children}
      </div>
    </div>
  );
};
