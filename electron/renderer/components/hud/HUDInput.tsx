import React, { InputHTMLAttributes } from 'react';

interface HUDInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  statusText?: string;
  statusClassName?: string;
}

export const HUDInput: React.FC<HUDInputProps> = ({ 
  label, 
  error, 
  statusText,
  statusClassName = 'text-text-secondary',
  className = '', 
  ...props 
}) => {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      {label && (
        <label className="font-display text-[10px] tracking-widest text-text-secondary uppercase mb-1 ml-1">
          {label}
        </label>
      )}
      <div className="relative group">
        <input
          className={`w-full bg-black/20 border-b border-white/20 px-3 py-2 font-mono text-sm text-text-primary placeholder-text-muted/50 focus:outline-none focus:border-accent-cyan focus:bg-accent-cyan/5 transition-all duration-300 rounded-t-sm ${statusText ? 'pr-24' : ''}`}
          {...props}
        />
        {statusText && (
          <span className={`pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] tracking-wider uppercase ${statusClassName}`}>
            {statusText}
          </span>
        )}
        {/* Animated bottom line on focus */}
        <div className="absolute bottom-0 left-0 w-0 h-px bg-accent-cyan transition-all duration-500 group-focus-within:w-full" />
      </div>
      {error && <span className="text-xs text-accent-red mt-1">{error}</span>}
    </div>
  );
};

export const HUDTextArea: React.FC<React.TextareaHTMLAttributes<HTMLTextAreaElement>> = ({ className = '', ...props }) => {
  return (
    <div className="relative group w-full">
       <textarea
          className={`w-full bg-black/20 border border-white/10 px-4 py-3 font-mono text-sm text-text-primary placeholder-text-muted/50 focus:outline-none focus:border-accent-cyan/50 focus:bg-accent-cyan/5 transition-all duration-300 rounded-sm resize-none ${className}`}
          {...props}
        />
         {/* Corner accents */}
         <div className="absolute top-0 left-0 w-2 h-2 border-l border-t border-accent-cyan/0 group-focus-within:border-accent-cyan/50 transition-colors duration-300 pointer-events-none" />
         <div className="absolute bottom-0 right-0 w-2 h-2 border-r border-b border-accent-cyan/0 group-focus-within:border-accent-cyan/50 transition-colors duration-300 pointer-events-none" />
    </div>
  );
};
