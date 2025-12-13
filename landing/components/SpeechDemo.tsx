import React, { useState, useEffect } from 'react';
import { PlayIcon, RefreshIcon, TagIcon } from './IconComponents';

const SpeechDemo: React.FC = () => {
    const [isRunning, setIsRunning] = useState(false);
    const [step, setStep] = useState(0); // 0: idle, 1: listening, 2: transcribed, 3: entities extracted
    const [transcript, setTranscript] = useState('');
    const [entities, setEntities] = useState<{label: string, value: string}[]>([]);
    
    const examplePhrase = "Подготовь отчет по новому проекту к завтрашнему дню.";

    useEffect(() => {
        if (isRunning) {
            setStep(1); // Start listening animation
            
            const timer1 = setTimeout(() => {
                setStep(2); // Show transcription
                setTranscript(examplePhrase);
            }, 2500); // Simulate 2.5s of speech

            const timer2 = setTimeout(() => {
                setStep(3); // Show entities
                setEntities([
                    {label: 'Тема', value: 'Проект'},
                    {label: 'Документ', value: 'Отчет'},
                    {label: 'Дата', value: 'Завтра'},
                ]);
                setIsRunning(false);
            }, 3500); // Show entities 1s after transcription

            return () => {
                clearTimeout(timer1);
                clearTimeout(timer2);
            };
        }
    }, [isRunning]);

    const handleRunDemo = () => {
        if (isRunning) return;
        setIsRunning(true);
        setTranscript('');
        setEntities([]);
        setStep(0);
    };
    
    const handleReset = () => {
        setIsRunning(false);
        setTranscript('');
        setEntities([]);
        setStep(0);
    }
    
    const isDemoFinished = step === 3 && !isRunning;

    return (
        <div className="bg-slate-800/50 rounded-xl border border-slate-700 shadow-lg overflow-hidden mt-12">
            <div className="p-8">
                <h3 className="text-2xl font-bold text-white mb-3">Демонстрация распознавания речи</h3>
                <p className="text-gray-400 mb-6">
                    Нажмите кнопку, чтобы симулировать распознавание фразы.
                    Система транскрибирует речь и извлечет ключевые сущности.
                </p>

                <div className="flex flex-col md:flex-row items-center gap-6">
                     <button
                        onClick={isDemoFinished ? handleReset : handleRunDemo}
                        className="bg-indigo-500 hover:bg-indigo-400 text-white font-bold py-3 px-8 rounded-full transition-all duration-300 transform hover:scale-105 shadow-lg shadow-indigo-500/30 disabled:bg-slate-600 disabled:scale-100 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                        disabled={isRunning}
                    >
                        {isRunning ? (
                             <>
                                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                <span>Выполнение...</span>
                            </>
                        ) : isDemoFinished ? (
                            <>
                                <RefreshIcon className="w-5 h-5" />
                                <span>Повторить</span>
                            </>
                        ) : (
                           <>
                                <PlayIcon className="w-5 h-5" />
                                <span>Запустить</span>
                           </>
                        )}
                    </button>
                    <div className="w-full text-center md:text-left min-h-[32px] flex items-center">
                        {step === 1 && (
                            <div className="flex items-center gap-3 w-full">
                                <div className="w-24 h-8 flex items-center justify-between animate-waveform">
                                    <span className="w-1 h-full bg-cyan-400 rounded-full"></span>
                                    <span className="w-1 h-full bg-cyan-400 rounded-full"></span>
                                    <span className="w-1 h-full bg-cyan-400 rounded-full"></span>
                                    <span className="w-1 h-full bg-cyan-400 rounded-full"></span>
                                    <span className="w-1 h-full bg-cyan-400 rounded-full"></span>
                                </div>
                                <p className="text-gray-400 italic">Симуляция аудиоввода...</p>
                            </div>
                        )}
                         {step > 1 && (
                             <p className="text-gray-400 italic">Процесс завершен.</p>
                         )}
                         {step === 0 && (
                             <p className="text-gray-400 italic">Готов к запуску демонстрации.</p>
                         )}
                    </div>
                </div>
            </div>

            {(step >= 2) && (
                <div className="bg-slate-900/50 p-8 border-t border-slate-700 space-y-6">
                    <div className={`transition-opacity duration-500 ${step >= 2 ? 'opacity-100' : 'opacity-0'}`}>
                        <h4 className="font-semibold text-white mb-2">Транскрипция:</h4>
                        <p className="text-gray-300 min-h-[2.5em] italic">"{transcript}"</p>
                    </div>
                    <div className={`transition-opacity duration-500 delay-200 ${step >= 3 ? 'opacity-100' : 'opacity-0'}`}>
                        <h4 className="font-semibold text-white mb-3">Извлеченные сущности:</h4>
                        <div className="flex flex-wrap gap-3">
                            {entities.map((entity, index) => (
                                <div key={index} className="flex items-center bg-slate-700 rounded-full px-4 py-1.5">
                                    <TagIcon className="w-5 h-5 mr-2 text-cyan-400" />
                                    <span className="text-sm text-gray-400 mr-1.5">{entity.label}:</span>
                                    <span className="text-sm font-medium text-white">{entity.value}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default SpeechDemo;