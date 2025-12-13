
import React from 'react';
import { HighlightedCitation } from '../types';

interface CitationCardProps {
  citation: HighlightedCitation;
}

const HighlightedText: React.FC<{ text: string }> = ({ text }) => {
    const parts = text.split(/<highlight>|<\/highlight>/g);
    return (
        <p className="text-sm text-gray-400">
            {parts.map((part, index) => 
                index % 2 === 1 ? (
                    <span key={index} className="bg-highlight text-gray-200 rounded px-1">
                        {part}
                    </span>
                ) : (
                    <span key={index}>{part}</span>
                )
            )}
        </p>
    );
};

const CitationCard: React.FC<CitationCardProps> = ({ citation }) => {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 flex flex-col gap-2 transition-all hover:border-teal-500">
        <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
                <span className="flex items-center justify-center w-6 h-6 text-sm font-bold bg-gray-600 text-white rounded-full">
                    {citation.source_id}
                </span>
                <span className="text-xs font-medium text-gray-300 truncate" title={citation.filename}>
                    {citation.filename}
                </span>
            </div>
            <span className="text-xs text-gray-500">Схожесть: {citation.score.toFixed(2)}</span>
        </div>
      <HighlightedText text={citation.highlighted_text} />
    </div>
  );
};

export default CitationCard;