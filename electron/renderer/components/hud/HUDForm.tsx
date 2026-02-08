import React, { InputHTMLAttributes, SelectHTMLAttributes } from 'react';

// HUD Checkbox - "X" inside a box style
interface HUDCheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export const HUDCheckbox: React.FC<HUDCheckboxProps> = ({ label, className = '', ...props }) => {
  return (
    <label className={`flex items-center gap-3 cursor-pointer group ${className}`}>
      <div className="relative w-5 h-5 flex items-center justify-center border border-white/20 bg-black/40 group-hover:border-accent-cyan/50 transition-colors duration-200 rounded-sm">
        <input 
          type="checkbox" 
          className="peer appearance-none w-full h-full cursor-pointer opacity-0 absolute inset-0 z-10"
          {...props}
        />
        {/* Unchecked state - empty or subtle dot */}
        <div className="w-1 h-1 bg-white/10 rounded-full" />
        
        {/* Checked state - The "X" or filled block */}
        <div className="absolute inset-0 flex items-center justify-center opacity-0 peer-checked:opacity-100 transition-opacity duration-200">
           <div className="w-3 h-3 bg-accent-cyan shadow-glow-sm" />
           {/* Alternative: SVG X icon if preferred */}
        </div>
        
        {/* Corner accents for the checkbox */}
        <div className="absolute top-0 left-0 w-1 h-1 border-t border-l border-white/30 group-hover:border-accent-cyan/50" />
        <div className="absolute bottom-0 right-0 w-1 h-1 border-b border-r border-white/30 group-hover:border-accent-cyan/50" />
      </div>
      <span className="font-display text-sm tracking-wide text-text-secondary group-hover:text-text-primary transition-colors select-none">
        {label}
      </span>
    </label>
  );
};

// HUD Select - Outlined technical dropdown
interface HUDSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { value: string; label: string }[];
}

export const HUDSelect: React.FC<HUDSelectProps> = ({ label, options, className = '', ...props }) => {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {label && (
        <span className="font-display text-[10px] tracking-widest text-text-secondary uppercase pl-1">
          {label}
        </span>
      )}
      <div className="relative group">
        <select
          className="w-full appearance-none bg-black/20 border border-white/10 px-4 py-2 pr-8 font-mono text-sm text-text-primary focus:outline-none focus:border-accent-cyan/50 focus:bg-accent-cyan/5 transition-all duration-200 rounded-sm"
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-bg-tertiary text-text-primary">
              {opt.label}
            </option>
          ))}
        </select>
        
        {/* Custom Arrow */}
        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-accent-cyan/50 group-hover:text-accent-cyan transition-colors">
          <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
            <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>

        {/* Corner Accents */}
        <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-accent-cyan/0 group-hover:border-accent-cyan/50 transition-colors" />
        <div className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-accent-cyan/0 group-hover:border-accent-cyan/50 transition-colors" />
      </div>
    </div>
  );
};
