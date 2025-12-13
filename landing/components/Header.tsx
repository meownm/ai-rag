import React, { useState, useEffect } from 'react';
import { BrainCircuitIcon, MenuIcon, XIcon } from './IconComponents';

const Header: React.FC = () => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);
  
  useEffect(() => {
    if (isMobileMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'auto';
    }
    return () => {
      document.body.style.overflow = 'auto';
    };
  }, [isMobileMenuOpen]);

  const navLinks = [
    { href: '#services', label: 'Услуги' },
    { href: '#technology', label: 'Технологии' },
    { href: '#use-cases', label: 'Примеры' },
    { href: '#about', label: 'О нас' },
    { href: '#contact', label: 'Контакты' },
  ];

  const handleLinkClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    const href = e.currentTarget.getAttribute('href');
    if (!href) return;

    const targetElement = document.querySelector(href);
    if (targetElement) {
        const header = document.querySelector('header');
        const headerHeight = header ? header.offsetHeight : 72; // Fallback header height
        const elementPosition = targetElement.getBoundingClientRect().top;
        const offsetPosition = elementPosition + window.pageYOffset - headerHeight;

        window.scrollTo({
            top: offsetPosition,
            behavior: 'smooth'
        });
    }
    
    setIsMobileMenuOpen(false);
  };
  
  const handleLogoClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    window.scrollTo({
      top: 0,
      behavior: 'smooth',
    });
    setIsMobileMenuOpen(false);
  }

  return (
    <>
      <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${isScrolled ? 'bg-slate-900/80 backdrop-blur-sm shadow-lg' : 'bg-transparent'}`}>
        <div className="container mx-auto px-6 py-4 flex justify-between items-center">
          <button type="button" onClick={handleLogoClick} className="flex items-center space-x-2">
            <BrainCircuitIcon className="w-8 h-8 text-cyan-400" />
            <span className="text-xl font-bold text-white">Контрактум</span>
          </button>
          <nav className="hidden md:flex space-x-8">
            {navLinks.map((link) => (
              <a key={link.href} href={link.href} onClick={handleLinkClick} className="text-gray-300 hover:text-cyan-400 transition-colors duration-300">
                {link.label}
              </a>
            ))}
          </nav>
          <div className="md:hidden">
            <button 
              onClick={() => setIsMobileMenuOpen(true)} 
              aria-label="Открыть меню"
              className="p-2 text-gray-300 hover:text-cyan-400 transition-colors"
            >
              <MenuIcon className="w-6 h-6" />
            </button>
          </div>
        </div>
      </header>

      {/* Mobile Menu Overlay */}
      <div 
        className={`fixed inset-0 bg-black/60 z-50 transition-opacity duration-300 md:hidden ${isMobileMenuOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
        onClick={() => setIsMobileMenuOpen(false)}
        aria-hidden="true"
      />

      {/* Mobile Menu Panel */}
      <div className={`fixed top-0 right-0 h-full w-64 bg-slate-900 shadow-2xl z-50 transform transition-transform duration-300 ease-in-out md:hidden ${isMobileMenuOpen ? 'translate-x-0' : 'translate-x-full'}`}>
        <div className="flex justify-end p-4">
          <button 
            onClick={() => setIsMobileMenuOpen(false)} 
            aria-label="Закрыть меню"
            className="p-2 text-gray-300 hover:text-cyan-400 transition-colors"
          >
            <XIcon className="w-6 h-6" />
          </button>
        </div>
        <nav className="flex flex-col p-4">
          {navLinks.map((link) => (
            <a 
              key={link.href} 
              href={link.href} 
              onClick={handleLinkClick}
              className="py-3 px-4 text-lg text-gray-300 hover:text-cyan-400 hover:bg-slate-800 rounded-md transition-colors duration-300"
            >
              {link.label}
            </a>
          ))}
        </nav>
      </div>
    </>
  );
};

export default Header;