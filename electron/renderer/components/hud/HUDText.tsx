import React, { ReactNode } from 'react';

interface TextProps {
  children: ReactNode;
  className?: string;
}

export const HUDHeader: React.FC<TextProps & { size?: 'sm' | 'md' | 'lg' | 'xl' }> = ({ 
  children, 
  className = '', 
  size = 'lg' 
}) => {
  const sizes = {
    sm: "text-base",
    md: "text-lg",
    lg: "text-2xl",
    xl: "text-4xl",
  };

  return (
    <h1 className={`font-display font-medium tracking-wide uppercase text-text-primary ${sizes[size]} ${className}`}>
      {children}
    </h1>
  );
};

export const HUDLabel: React.FC<TextProps> = ({ children, className = '' }) => {
  return (
    <span className={`font-display text-[10px] tracking-[0.2em] text-text-secondary uppercase ${className}`}>
      {children}
    </span>
  );
};

// Extremely small technical label
export const HUDMicro: React.FC<TextProps> = ({ children, className = '' }) => {
  return (
    <span className={`font-mono text-[9px] tracking-[0.1em] text-white/30 uppercase ${className}`}>
      {children}
    </span>
  );
};

export const HUDValue: React.FC<TextProps & { glow?: boolean }> = ({ 
  children, 
  className = '',
  glow = false
}) => {
  return (
    <span className={`font-mono text-text-primary ${glow ? 'text-shadow-glow text-accent-cyan' : ''} ${className}`}>
      {children}
    </span>
  );
};

export const HUDSectionTitle: React.FC<TextProps & { number?: string }> = ({ children, number, className = '' }) => {
  return (
    <div className={`flex items-baseline gap-3 mb-4 border-b border-white/10 pb-2 ${className}`}>
      {number && <span className="font-mono text-accent-cyan text-xs opacity-70">{number}</span>}
      <h2 className="font-display text-sm tracking-widest text-text-primary uppercase">
        {children}
      </h2>
      <div className="flex-1 h-px bg-white/5 relative top-[-4px]">
        <div className="absolute right-0 top-0 w-8 h-px bg-accent-cyan/30" />
      </div>
    </div>
  );
};
