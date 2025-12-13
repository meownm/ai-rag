import React from 'react';
import RagDemo from './RagDemo';
import SpeechDemo from './SpeechDemo';

const Demo: React.FC = () => {
    return (
        <section id="demo" className="py-20 bg-slate-900">
            <div className="container mx-auto px-6">
                <div className="text-center mb-16">
                    <h2 className="text-4xl font-extrabold text-white">Интерактивное демо</h2>
                    <p className="text-lg text-gray-400 mt-2">Посмотрите, как наши технологии работают в действии.</p>
                </div>

                <RagDemo />
                <SpeechDemo />
            </div>
        </section>
    );
};

export default Demo;
