import React from 'react';
import { HUDButton } from './HUDButton';

interface Tab {
  id: string;
  label: string;
  icon: string;
}

interface HUDNavBarProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (id: string) => void;
  badges?: Record<string, number>;
}

export const HUDNavBar: React.FC<HUDNavBarProps> = ({ tabs, activeTab, onTabChange, badges }) => {
  return (
    <div className="flex justify-center items-center py-4 relative z-50">
      {/* Decorative center line */}
      <div className="absolute top-1/2 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent -z-10" />

      <div className="flex gap-4 p-2 bg-black/40 backdrop-blur-md rounded-full border border-white/5 shadow-glass">
        {tabs.map((tab) => {
          const badgeCount = badges?.[tab.id] ?? 0;
          return (
            <div key={tab.id} className="relative">
              <HUDButton
                variant={activeTab === tab.id ? 'primary' : 'ghost'}
                onClick={() => onTabChange(tab.id)}
                className="min-w-[120px]"
                icon={<span className="text-lg leading-none mb-0.5">{tab.icon}</span>}
              >
                {tab.label}
              </HUDButton>
              {badgeCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-accent-cyan rounded-full animate-pulse shadow-[0_0_6px_rgba(0,212,255,0.6)]" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
