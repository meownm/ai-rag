import React from 'react';

const Hero: React.FC = () => {
  return (
    <section id="hero" className="relative pt-32 pb-20 md:pt-40 md:pb-28 flex items-center justify-center text-center overflow-hidden">
       <div className="absolute inset-0 bg-slate-900 bg-[linear-gradient(to_right,#4f4f4f2e_1px,transparent_1px),linear-gradient(to_bottom,#4f4f4f2e_1px,transparent_1px)] bg-[size:14px_24px]"></div>
       <div className="absolute inset-0 hero-background-gradient"></div>

      <div className="relative z-10 container mx-auto px-6">
        <h1 className="text-4xl md:text-6xl lg:text-7xl font-extrabold text-white mb-4 leading-tight">
          <span className="text-cyan-400">Системы ответов по базам знаний</span> и <span className="text-indigo-400">распознавание речи</span>
        </h1>
        <p className="text-lg md:text-xl text-gray-300 max-w-3xl mx-auto mb-8">
          Мы превращаем ваши данные и голос в мощные бизнес-инструменты, открывая новые возможности для роста и эффективности.
        </p>
        <a 
          href="#contact" 
          className="bg-cyan-500 hover:bg-cyan-400 text-white font-bold py-3 px-8 rounded-full text-lg transition-all duration-300 transform hover:scale-105 shadow-lg shadow-cyan-500/30"
        >
          Обсудить проект
        </a>
      </div>
    </section>
  );
};

export default Hero;