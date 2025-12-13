import React from 'react';
import Header from './components/Header';
import Hero from './components/Hero';
import Services from './components/Services';
import Technology from './components/Technology';
import UseCases from './components/UseCases';
import About from './components/About';
import Contact from './components/Contact';
import Footer from './components/Footer';

const App: React.FC = () => {
  return (
    <div className="bg-slate-900 text-gray-200 font-sans antialiased">
      <Header />
      <main>
        <Hero />
        <Services />
        <Technology />
        <UseCases />
        <About />
        <Contact />
      </main>
      <Footer />
    </div>
  );
};

export default App;