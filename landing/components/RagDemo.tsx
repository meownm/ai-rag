import React, { useState, useEffect } from 'react';
import { DocumentTextIcon, SparklesIcon, PlayIcon, RefreshIcon } from './IconComponents';

const RagDemo: React.FC = () => {
    const query = 'Каковы преимущества этой технологии?';
    const [retrievedDocs, setRetrievedDocs] = useState<string[]>([]);
    const [generatedAnswer, setGeneratedAnswer] = useState('');
    const [isRunning, setIsRunning] = useState(false);
    const [step, setStep] = useState(0); // 0: idle, 1: query, 2: docs, 3: answer

    useEffect(() => {
        if (isRunning) {
            setStep(1); // Show query
            const timer1 = setTimeout(() => {
                 const docs = [
                    "Документ 1: Системы ответов по базам знаний значительно повышают точность ответов, так как они основываются на фактической информации из проверенной базы знаний, а не только на общих данных, на которых обучалась модель.",
                    "Документ 2: Ключевое преимущество — снижение вероятности 'галлюцинаций'. Предоставляя модели релевантный контекст, мы направляем её генерацию и обеспечиваем фактологическую достоверность.",
                    "Документ 3: Внедрение таких систем позволяет AI использовать самую актуальную информацию без необходимости полного переобучения, что делает систему гибкой и экономически эффективной."
                ];
                setRetrievedDocs(docs);
                setStep(2); // Show docs
            }, 1000);

            const timer2 = setTimeout(() => {
                 const answer = "На основе найденных документов, системы ответов по базам знаний повышают точность ответов и снижают риск 'галлюцинаций', предоставляя языковой модели актуальный и проверенный контекст из вашей базы знаний. Это также делает систему более гибкой и экономичной.";
                setGeneratedAnswer(answer);
                setStep(3); // Show answer
                setIsRunning(false);
            }, 2500);

            return () => {
                clearTimeout(timer1);
                clearTimeout(timer2);
            };
        }
    }, [isRunning]);

    const handleRunDemo = () => {
        if (isRunning) return;
        setIsRunning(true);
        setRetrievedDocs([]);
        setGeneratedAnswer('');
        setStep(0);
    };
    
    const handleReset = () => {
        setIsRunning(false);
        setRetrievedDocs([]);
        setGeneratedAnswer('');
        setStep(0);
    }

    const stepClass = (s: number) => `transition-all duration-500 ${step >= s ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4 pointer-events-none'}`;
    const isDemoFinished = step === 3 && !isRunning;

    return (
        <div className="bg-slate-800/50 rounded-xl border border-slate-700 shadow-lg overflow-hidden">
            <div className="p-8">
                <h3 className="text-2xl font-bold text-white mb-3">Демонстрация системы ответов</h3>
                <p className="text-gray-400 mb-6">Нажмите кнопку, чтобы увидеть, как система находит релевантные документы в базе знаний и генерирует на их основе точный ответ.</p>
                
                <button
                    onClick={isDemoFinished ? handleReset : handleRunDemo}
                    className="bg-cyan-500 hover:bg-cyan-400 text-white font-bold py-3 px-8 rounded-full transition-all duration-300 transform hover:scale-105 shadow-lg shadow-cyan-500/30 disabled:bg-slate-600 disabled:scale-100 disabled:cursor-not-allowed flex items-center justify-center gap-2"
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
            </div>
            
            {step > 0 && (
                 <div className="bg-slate-900/50 p-8 border-t border-slate-700 space-y-8">
                    <div className={stepClass(1)}>
                        <h4 className="font-semibold text-white mb-3">1. Вопрос пользователя:</h4>
                        <p className="text-gray-300 italic">"{query}"</p>
                    </div>

                    <div className={stepClass(2)}>
                        <h4 className="font-semibold text-white mb-3 flex items-center gap-2">
                            <DocumentTextIcon className="w-5 h-5 text-cyan-400" />
                            2. Найдено в базе знаний:
                        </h4>
                        <div className="space-y-4">
                            {retrievedDocs.map((doc, index) => (
                                <p key={index} className="bg-slate-800 p-4 rounded-lg border border-slate-700 text-gray-400 text-sm">
                                    {doc}
                                </p>
                            ))}
                        </div>
                    </div>

                    <div className={stepClass(3)}>
                        <h4 className="font-semibold text-white mb-3 flex items-center gap-2">
                            <SparklesIcon className="w-5 h-5 text-indigo-400" />
                            3. Сгенерированный ответ:
                        </h4>
                        <p className="text-gray-200 bg-gradient-to-r from-cyan-500/10 to-indigo-500/10 p-4 rounded-lg border border-slate-700">
                            {generatedAnswer}
                        </p>
                    </div>
                </div>
            )}
        </div>
    );
};

export default RagDemo;