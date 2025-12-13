

import React, { useState } from 'react';
import ChatView from './components/ChatView';
import Sidebar from './components/Sidebar';
import { ConversationInfo } from './types';

const App: React.FC = () => {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);

  const handleNewChat = () => {
    setActiveConversationId(null);
  };

  const handleSelectConversation = (conversation: ConversationInfo) => {
    setActiveConversationId(conversation.conversation_id);
    console.log("Selected conversation:", conversation.conversation_id);
  };

  return (
    <div className="flex h-screen font-sans">
      <Sidebar 
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
      /> 
      <main className="flex-1 flex flex-col bg-gray-900">
        <ChatView key={activeConversationId || 'new-chat'} conversationId={activeConversationId} />
      </main>
    </div>
  );
};

export default App;