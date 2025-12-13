
import React from 'react';

const Footer: React.FC = () => {
  return (
    <footer className="bg-slate-800/40 border-t border-slate-800">
      <div className="container mx-auto px-6 py-6 text-center text-gray-500">
        <p>&copy; {new Date().getFullYear()} Контрактум. Все права защищены.</p>
      </div>
    </footer>
  );
};

export default Footer;