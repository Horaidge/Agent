'use client';

import { motion } from 'framer-motion';

interface InfoPanelProps {
  section: string | null;
  onClose: () => void;
}

export function InfoPanel({ section, onClose }: InfoPanelProps) {
  // Define distinct content for each section
  const sections = {
    Platform: {
      title: 'Platform',
      subtitle: 'Multi-Agent AI System',
      items: [
        'Smart Knowledge Base — contextual understanding',
        'Agents that act, not just answer',
        'Voice, text, visual, systems integration',
        'Real-time orchestration & decision making'
      ]
    },
    'Use Cases': {
      title: 'Use Cases',
      subtitle: 'Enterprise Applications',
      items: [
        'Customer support automation',
        'Internal workflows & processes',
        'Document processing & analysis',
        'Omnichannel assistants',
        'Digital twins & avatars'
      ]
    },
    'How It Works': {
      title: 'How It Works',
      subtitle: 'Architecture & Orchestration',
      items: [
        'Router Agent — intelligent request routing',
        'Knowledge Agent — RAG-powered retrieval',
        'Skill Agent — task execution & transactions',
        'Multi-layer RAG — semantic understanding',
        'Orchestration logic — decision flow'
      ]
    }
  };

  const content = sections[section as keyof typeof sections];

  if (!content) return null;

  return (
    <motion.div
      className="relative z-15 w-full"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      {/* Close button row */}
      <div className="flex items-center justify-between px-6 py-4 mb-2 bg-gradient-to-b from-[rgba(12,13,20,0.4)] to-transparent">
        <h2 className="text-lg font-semibold text-foreground">{content.title}</h2>
        <button
          onClick={onClose}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors focus:outline-none"
          aria-label="Close info panel"
        >
          Close
        </button>
      </div>

      {/* Content card */}
      <div className="mx-6 p-6 rounded-xl bg-card border border-border/30 shadow-lg">
        <p className="text-sm text-muted-foreground mb-4 font-light">{content.subtitle}</p>

        {/* Item list */}
        <ul className="space-y-3">
          {content.items.map((item, idx) => (
            <motion.li
              key={idx}
              className="flex items-start gap-3 text-sm text-foreground/80"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.05, duration: 0.25 }}
            >
              <span
                className="flex-shrink-0 w-1.5 h-1.5 rounded-full mt-2"
                style={{ backgroundColor: 'rgba(124, 58, 237, 0.4)' }}
              />
              <span>{item}</span>
            </motion.li>
          ))}
        </ul>
      </div>
    </motion.div>
  );
}
