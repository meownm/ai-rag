

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
    // This is a placeholder. In a full app, you'd fetch the conversation messages.
    // For this example, selecting a conversation just shows its title but starts a new chat context.
    setActiveConversationId(conversation.conversation_id);
    console.log("Selected conversation:", conversation.conversation_id);
    // To keep the demo simple, we will reset the view for a "new" chat
    // under the selected conversation context.
    setActiveConversationId(null); 
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