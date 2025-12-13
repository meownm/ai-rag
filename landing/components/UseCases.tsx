
import React from 'react';

const UseCaseCard: React.FC<{ title: string; }> = ({ title }) => (
  <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 text-center transition duration-300 hover:bg-slate-700/50">
    <p className="text-lg font-semibold text-white">{title}</p>
  </div>
);

const UseCases: React.FC = () => {
  const cases = [
    "Умный поиск по корпоративной базе знаний",
    "Автоматизация поддержки клиентов 24/7",
    "Анализ записей звонков и встреч",
    "Голосовые помощники и IVR-системы",
    "Создание отчетов и саммари из документов",
    "Контроль качества обслуживания",
  ];

  return (
    <section id="use-cases" className="py-20 bg-slate-900">
      <div className="container mx-auto px-6">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-extrabold text-white">Примеры применения</h2>
          <p className="text-lg text-gray-400 mt-2">Решаем реальные бизнес-задачи в различных отраслях.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {cases.map((useCase, index) => (
            <UseCaseCard key={index} title={useCase} />
          ))}
        </div>
      </div>
    </section>
  );
};

export default UseCases;