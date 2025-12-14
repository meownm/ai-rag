import React, { useMemo, useState } from 'react';
import ChatView from './components/ChatView';
import Sidebar from './components/Sidebar';
import ProfileView from './components/ProfileView';
import AdminPanel from './components/AdminPanel';
import { ConversationInfo } from './types';

type Section = 'chat' | 'profile' | 'admin';

const App: React.FC = () => {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [section, setSection] = useState<Section>('chat');

  const handleNewChat = () => {
    setActiveConversationId(null);
    setSection('chat');
  };

  const handleSelectConversation = (conversation: ConversationInfo) => {
    setActiveConversationId(conversation.conversation_id);
    setSection('chat');
  };

  const renderContent = useMemo(() => {
    if (section === 'profile') {
      return <ProfileView />;
    }
    if (section === 'admin') {
      return <AdminPanel />;
    }
    return <ChatView key={activeConversationId || 'new-chat'} conversationId={activeConversationId} />;
  }, [activeConversationId, section]);

  const title = section === 'chat' ? 'Чат' : section === 'profile' ? 'Мой профиль' : 'Администрирование';

  return (
    <div className="flex h-screen font-sans">
      <Sidebar
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        activeSection={section}
        onChangeSection={setSection}
      />
      <main className="flex-1 flex flex-col bg-gray-900">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-gray-900/80 sticky top-0">
          <div>
            <p className="text-sm text-gray-400">RAG Search</p>
            <h1 className="text-2xl font-semibold text-white">{title}</h1>
          </div>
        </div>
        {renderContent}
      </main>
    </div>
  );
};

export default App;
