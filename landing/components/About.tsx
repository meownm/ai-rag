
import React from 'react';

const About: React.FC = () => {
  return (
    <section id="about" className="py-20 bg-slate-800/40">
      <div className="container mx-auto px-6 text-center max-w-3xl">
        <h2 className="text-4xl font-extrabold text-white mb-6">О нас</h2>
        <p className="text-lg text-gray-300 leading-relaxed">
          Мы — команда экспертов в области искусственного интеллекта и машинного обучения, увлеченных созданием продуктов, которые приносят реальную пользу. 
          Наша миссия — демократизировать доступ к передовым AI-технологиям, помогая компаниям любого размера внедрять интеллектуальные решения для оптимизации процессов и создания инновационных сервисов.
        </p>
      </div>
    </section>
  );
};

export default About;