
import React from 'react';
import { AnswerRequest, SearchMode } from '../types';

type Options = Omit<AnswerRequest, 'query' | 'conversation_id' | 'stream'>;

interface SearchOptionsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  options: Options;
  setOptions: React.Dispatch<React.SetStateAction<Options>>;
}

const SearchOptionsPanel: React.FC<SearchOptionsPanelProps> = ({ isOpen, onClose, options, setOptions }) => {
  if (!isOpen) return null;

  const handleOptionChange = <K extends keyof Options>(key: K, value: Options[K]) => {
    setOptions(prev => ({ ...prev, [key]: value }));
  };

  const searchModes: SearchMode[] = ["dense", "bm25", "hybrid", "graph", "hybrid+graph"];

  return (
    <>
      <div 
        className="fixed inset-0 bg-black/60 z-40 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      ></div>
      <div 
        className={`fixed top-0 bottom-0 right-0 w-full max-w-sm bg-gray-800 border-l border-gray-700 shadow-xl z-50 transform transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="options-panel-title"
      >
        <div className="p-6 h-full flex flex-col">
          <div className="flex items-center justify-between mb-6">
            <h2 id="options-panel-title" className="text-xl font-semibold text-white">Опции Поиска</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-white">&times;</button>
          </div>
          
          <div className="space-y-6 flex-1 overflow-y-auto pr-2">
            <div>
              <label htmlFor="search-mode" className="block text-sm font-medium text-gray-300 mb-2">Режим поиска</label>
              <select
                id="search-mode"
                value={options.mode}
                onChange={(e) => handleOptionChange('mode', e.target.value as SearchMode)}
                className="w-full bg-gray-700 border border-gray-600 rounded-md py-2 px-3 text-white focus:ring-teal-500 focus:border-teal-500"
              >
                {searchModes.map(mode => <option key={mode} value={mode}>{mode}</option>)}
              </select>
            </div>

            <div>
              <label htmlFor="top-k" className="block text-sm font-medium text-gray-300 mb-2">Топ K чанков: {options.top_k}</label>
              <input
                id="top-k"
                type="range"
                min="1"
                max="20"
                step="1"
                value={options.top_k}
                onChange={(e) => handleOptionChange('top_k', parseInt(e.target.value, 10))}
                className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer"
              />
            </div>
            
             <div>
              <label htmlFor="graph-depth" className="block text-sm font-medium text-gray-300 mb-2">Глубина графа: {options.graph_depth}</label>
              <input
                id="graph-depth"
                type="range"
                min="1"
                max="5"
                step="1"
                value={options.graph_depth}
                onChange={(e) => handleOptionChange('graph_depth', parseInt(e.target.value, 10))}
                className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer"
              />
            </div>

            <div className="border-t border-gray-700 pt-6">
                <h3 className="text-lg font-medium text-white mb-4">Фильтры</h3>
                <p className="text-sm text-gray-500">Управление фильтрами еще не реализовано в этой версии интерфейса.</p>
            </div>

          </div>
        </div>
      </div>
    </>
  );
};

export default SearchOptionsPanel;