import React from 'react';
import { BrainCircuitIcon, MicrophoneIcon } from './IconComponents';

const ServiceCard: React.FC<{ icon: React.ReactNode; title: string; description: string; }> = ({ icon, title, description }) => (
  <div className="bg-slate-800/50 p-8 rounded-xl border border-slate-700 shadow-lg hover:border-cyan-400 hover:scale-105 transition-all duration-300">
    <div className="mb-4 text-cyan-400">{icon}</div>
    <h3 className="text-2xl font-bold text-white mb-3">{title}</h3>
    <p className="text-gray-400 leading-relaxed">{description}</p>
  </div>
);

const Services: React.FC = () => {
  return (
    <section id="services" className="py-20 bg-slate-900">
      <div className="container mx-auto px-6">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-extrabold text-white">Наши услуги</h2>
          <p className="text-lg text-gray-400 mt-2">Создаем передовые AI-решения для вашего бизнеса.</p>
        </div>
        <div className="grid md:grid-cols-2 gap-8">
          <ServiceCard
            icon={<BrainCircuitIcon className="w-12 h-12" />}
            title="Системы ответов по базам знаний"
            description="Разрабатываем и внедряем системы, которые предоставляют точные, контекстно-зависимые ответы, основываясь на вашей базе знаний, документах и данных. Идеально для чат-ботов, внутреннего поиска и аналитики."
          />
          <ServiceCard
            icon={<MicrophoneIcon className="w-12 h-12" />}
            title="Распознавание речи"
            description="Наши решения преобразуют аудиопотоки в текст в реальном времени или в записи. Мы обеспечиваем высокую точность транскрибации, анализ тональности и извлечение ключевых инсайтов из телефонных звонков, встреч и голосовых команд."
          />
        </div>
      </div>
    </section>
  );
};

export default Services;