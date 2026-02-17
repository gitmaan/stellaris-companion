import React, { ButtonHTMLAttributes } from 'react';

interface HUDButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  icon?: React.ReactNode;
}

export const HUDButton: React.FC<HUDButtonProps> = ({ 
  children, 
  variant = 'primary', 
  className = '', 
  icon,
  ...props 
}) => {
  const baseClasses = "group relative inline-flex items-center justify-center px-6 py-2 rounded-lg font-display text-xs tracking-widest uppercase transition-all duration-200 outline-none disabled:opacity-50 disabled:cursor-not-allowed";
  
  const variants = {
    primary: "bg-accent-cyan/10 border border-accent-cyan/40 text-accent-cyan hover:bg-accent-cyan/20 hover:border-accent-cyan hover:shadow-glow-sm active:translate-y-px",
    secondary: "bg-transparent border border-white/20 text-text-secondary hover:text-text-primary hover:border-white/40 active:translate-y-px",
    ghost: "bg-transparent border border-transparent text-text-secondary hover:text-accent-cyan hover:bg-accent-cyan/5",
    danger: "bg-accent-red/10 border border-accent-red/40 text-accent-red hover:bg-accent-red/20 hover:border-accent-red hover:shadow-glow-red",
  };

  return (
    <button 
      className={`${baseClasses} ${variants[variant]} ${className}`}
      {...props}
    >
      {/* Hover Brackets Effect */}
      {variant === 'primary' && (
        <>
          <span className="absolute left-0 top-0 h-2 w-2 border-l border-t border-accent-cyan opacity-0 transition-opacity group-hover:opacity-100" />
          <span className="absolute right-0 bottom-0 h-2 w-2 border-r border-b border-accent-cyan opacity-0 transition-opacity group-hover:opacity-100" />
        </>
      )}

      {icon && <span className="mr-2 opacity-80 group-hover:opacity-100 transition-opacity">{icon}</span>}
      <span className="relative z-10">{children}</span>
    </button>
  );
};
