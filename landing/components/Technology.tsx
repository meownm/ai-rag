import React from 'react';
import { DatabaseIcon, SearchIcon, ChatIcon } from './IconComponents';

const TechStep: React.FC<{ icon: React.ReactNode; title: string; description: string; }> = ({ icon, title, description }) => (
  <div className="flex flex-col items-center text-center p-4">
    <div className="p-4 bg-slate-700 rounded-full mb-4 border-2 border-slate-600 text-cyan-300">
      {icon}
    </div>
    <h3 className="text-xl font-semibold text-white mb-2">{title}</h3>
    <p className="text-gray-400">{description}</p>
  </div>
);

const Technology: React.FC = () => {
  return (
    <section id="technology" className="py-20 bg-slate-800/40">
      <div className="container mx-auto px-6">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-extrabold text-white">Как это работает</h2>
          <p className="text-lg text-gray-400 mt-2">Прозрачный и эффективный процесс от данных к ответу.</p>
        </div>
        <div className="flex flex-col md:flex-row justify-center items-start space-y-8 md:space-y-0 md:space-x-8">
            <TechStep 
                icon={<DatabaseIcon className="w-10 h-10" />}
                title="1. Индексация данных"
                description="Мы обрабатываем и индексируем ваши документы, создавая векторную базу знаний."
            />
            <div className="hidden md:block text-slate-600 text-4xl mt-12 font-thin">&rarr;</div>
            <TechStep 
                icon={<SearchIcon className="w-10 h-10" />}
                title="2. Поиск информации"
                description="При поступлении запроса система находит наиболее релевантные фрагменты информации."
            />
            <div className="hidden md:block text-slate-600 text-4xl mt-12 font-thin">&rarr;</div>
            <TechStep 
                icon={<ChatIcon className="w-10 h-10" />}
                title="3. Генерация ответа"
                description="Большая языковая модель (LLM) использует найденный контекст для генерации точного ответа."
            />
        </div>
      </div>
    </section>
  );
};

export default Technology;