import React, { ReactNode } from 'react';

interface HUDPanelProps {
  children: ReactNode;
  title?: string;
  className?: string;
  variant?: 'primary' | 'secondary' | 'alert' | 'glass';
  decoration?: 'none' | 'brackets' | 'tech' | 'scanline';
  noPadding?: boolean;
  quiet?: boolean;
}

export const HUDPanel: React.FC<HUDPanelProps> = ({ 
  children, 
  title, 
  className = '', 
  variant = 'primary',
  decoration = 'none',
  noPadding = false,
  quiet = false,
}) => {
  const baseClasses = "relative rounded-sm overflow-hidden backdrop-blur-md transition-all duration-300";
  
  const variantClasses = {
    primary: "bg-bg-glass border border-border-subtle hover:border-accent-cyan/30",
    secondary: "bg-bg-tertiary/40 border border-white/5",
    alert: "bg-accent-red/10 border border-accent-red/30 shadow-glow-red-soft",
    glass: "bg-black/20 border border-white/5 shadow-glass",
  };

  // Border override for 'brackets' style - we remove the full border
  const finalVariantClass = decoration === 'brackets' 
    ? variantClasses[variant].replace('border border-border-subtle', '').replace('border border-white/5', '') 
    : variantClasses[variant];
  const cornerClass = quiet ? 'w-2 h-2 border-accent-cyan/35' : 'w-3 h-3 border-accent-cyan opacity-70';
  const cornerBorderClass = quiet ? 'border-l border-t' : 'border-l-2 border-t-2';
  const cornerBottomBorderClass = quiet ? 'border-l border-b' : 'border-l-2 border-b-2';
  const cornerRightClass = quiet ? 'border-r border-t' : 'border-r-2 border-t-2';
  const cornerBottomRightClass = quiet ? 'border-r border-b' : 'border-r-2 border-b-2';

  return (
    <div className={`${baseClasses} ${finalVariantClass} ${className}`}>
      
      {/* Decoration: Brackets (Corners only) */}
      {(decoration === 'brackets' || variant === 'primary') && (
        <>
          <div className={`absolute top-0 left-0 ${cornerClass} ${cornerBorderClass} pointer-events-none`} />
          <div className={`absolute top-0 right-0 ${cornerClass} ${cornerRightClass} pointer-events-none`} />
          <div className={`absolute bottom-0 left-0 ${cornerClass} ${cornerBottomBorderClass} pointer-events-none`} />
          <div className={`absolute bottom-0 right-0 ${cornerClass} ${cornerBottomRightClass} pointer-events-none`} />
        </>
      )}

      {/* Decoration: Tech (Header bar with ticks) */}
      {decoration === 'tech' && (
        <div className={`absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-cyan/40 to-transparent pointer-events-none ${quiet ? 'opacity-25' : 'opacity-50'}`}>
           <div className={`absolute top-0 left-1/4 w-px bg-accent-cyan ${quiet ? 'h-1 opacity-50' : 'h-2'}`} />
           <div className={`absolute top-0 right-1/4 w-px bg-accent-cyan ${quiet ? 'h-1 opacity-50' : 'h-2'}`} />
        </div>
      )}

      {/* Decoration: Scanline Animation */}
      {decoration === 'scanline' && (
        <div className="absolute inset-0 bg-scanline opacity-5 pointer-events-none z-0" />
      )}

      {title && (
        <div className={`flex items-center justify-between px-4 border-b border-white/5 relative z-10 ${quiet ? 'py-2.5 bg-white/[0.025]' : 'py-3 bg-white/5'}`}>
          <h3 className={`font-display text-xs tracking-tech uppercase ${quiet ? 'text-accent-cyan/80' : 'text-accent-cyan text-glow-sm'}`}>
            {title}
          </h3>
          {/* Decorative lines next to title */}
          <div className={`h-px flex-1 bg-gradient-to-r from-accent-cyan/20 to-transparent ml-4 relative ${quiet ? 'opacity-50' : ''}`}>
             <div className={`absolute right-0 top-1/2 -translate-y-1/2 rounded-full ${quiet ? 'w-0.5 h-0.5 bg-accent-cyan/30' : 'w-1 h-1 bg-accent-cyan/50'}`} />
          </div>
        </div>
      )}

      <div className={`relative z-10 ${noPadding ? 'h-full' : 'p-4'}`}>
        {children}
      </div>
    </div>
  );
};
