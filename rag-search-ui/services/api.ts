

import { AnswerRequest, StreamChunk, ConversationInfo, UserProfile, AdminUser, Invite, UserRole } from '../types';

// The backend is expected to be running on this URL.
// In a real-world scenario, this would come from an environment variable.
const API_BASE_URL = 'http://localhost:8020';

let mockProfile: UserProfile = {
  id: 'user-1',
  name: 'Анна Смирнова',
  email: 'anna@example.com',
  organization: 'Acme Corp',
  role: 'editor',
  telegramUsername: null,
};

let mockUsers: AdminUser[] = [
  {
    ...mockProfile,
    status: 'active',
    lastActivity: new Date().toISOString(),
  },
  {
    id: 'user-2',
    name: 'Виктор Сергеев',
    email: 'victor@example.com',
    organization: 'Acme Corp',
    role: 'viewer',
    telegramUsername: '@victor',
    status: 'invited',
    lastActivity: new Date(Date.now() - 3600 * 1000).toISOString(),
  },
];

let mockInvites: Invite[] = [];

export const getAnswerStream = async (
  request: AnswerRequest,
  onChunk: (chunk: StreamChunk) => void,
  onError: (error: Error) => void,
  onClose: () => void
) => {
  try {
    const response = await fetch(`${API_BASE_URL}/v1/answer`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream'
      },
      body: JSON.stringify({ ...request, stream: true }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API Error: ${response.status} ${response.statusText} - ${errorText}`);
    }

    if (!response.body) {
      throw new Error('Response body is null');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      
      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i];
        if (line.startsWith('data: ')) {
          try {
            const jsonData = JSON.parse(line.substring(6));
            onChunk(jsonData as StreamChunk);
          } catch (e) {
            console.error('Failed to parse SSE data chunk:', line, e);
          }
        }
      }
      buffer = lines[lines.length - 1];
    }
  } catch (error) {
    onError(error instanceof Error ? error : new Error('An unknown error occurred'));
  } finally {
    onClose();
  }
};

export const getHistoryList = async (
  userId: string,
  limit: number = 20,
  offset: number = 0
): Promise<ConversationInfo[]> => {
  const response = await fetch(`${API_BASE_URL}/v1/history?user_id=${encodeURIComponent(userId)}&limit=${limit}&offset=${offset}`, {
    method: 'GET',
    headers: {
      'Accept': 'application/json'
    }
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch history: ${response.status} ${response.statusText} - ${errorText}`);
  }

  const data: ConversationInfo[] = await response.json();
  return data;
};

export const clearHistory = async (userId: string): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/v1/history?user_id=${encodeURIComponent(userId)}`, {
    method: 'DELETE',
    headers: {
      'Accept': 'application/json'
    }
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to clear history: ${response.status} ${response.statusText} - ${errorText}`);
  }
};

export const getUserProfile = async (): Promise<UserProfile> => {
  return new Promise(resolve => {
    setTimeout(() => resolve({ ...mockProfile }), 200);
  });
};

export const linkTelegram = async (username: string): Promise<UserProfile> => {
  mockProfile = { ...mockProfile, telegramUsername: username.startsWith('@') ? username : `@${username}` };
  mockUsers = mockUsers.map(user => user.id === mockProfile.id ? { ...user, telegramUsername: mockProfile.telegramUsername } : user);
  return getUserProfile();
};

export const unlinkTelegram = async (): Promise<UserProfile> => {
  mockProfile = { ...mockProfile, telegramUsername: null };
  mockUsers = mockUsers.map(user => user.id === mockProfile.id ? { ...user, telegramUsername: null } : user);
  return getUserProfile();
};

export const getUsers = async (): Promise<AdminUser[]> => {
  return new Promise(resolve => setTimeout(() => resolve([...mockUsers]), 150));
};

export const updateUserRole = async (userId: string, role: UserRole): Promise<AdminUser> => {
  mockUsers = mockUsers.map(user => user.id === userId ? { ...user, role } : user);
  if (mockProfile.id === userId) {
    mockProfile = { ...mockProfile, role };
  }
  const updatedUser = mockUsers.find(user => user.id === userId);
  if (!updatedUser) {
    throw new Error('Пользователь не найден');
  }
  return new Promise(resolve => setTimeout(() => resolve(updatedUser), 150));
};

export const resetPassword = async (userId: string): Promise<void> => {
  return new Promise(resolve => setTimeout(resolve, 150));
};

export const resetTwoFactor = async (userId: string): Promise<void> => {
  return new Promise(resolve => setTimeout(resolve, 150));
};

export const getInvites = async (): Promise<Invite[]> => {
  return new Promise(resolve => setTimeout(() => resolve([...mockInvites]), 150));
};

export const createEmailInvite = async (email: string, invitedBy: string): Promise<Invite> => {
  const invite: Invite = {
    id: `invite-${Date.now()}`,
    email,
    link: `https://example.com/invite/${btoa(email)}`,
    createdAt: new Date().toISOString(),
    invitedBy,
    status: 'pending',
    type: 'email',
  };
  mockInvites = [invite, ...mockInvites];
  return new Promise(resolve => setTimeout(() => resolve(invite), 150));
};

export const createLinkInvite = async (invitedBy: string): Promise<Invite> => {
  const token = Math.random().toString(36).substring(2, 8);
  const invite: Invite = {
    id: `invite-${Date.now()}`,
    link: `https://example.com/invite/${token}`,
    createdAt: new Date().toISOString(),
    invitedBy,
    status: 'pending',
    type: 'link',
  };
  mockInvites = [invite, ...mockInvites];
  return new Promise(resolve => setTimeout(() => resolve(invite), 150));
};
