

import { AnswerRequest, StreamChunk, ConversationInfo } from '../types';

// The backend is expected to be running on this URL.
// In a real-world scenario, this would come from an environment variable.
const API_BASE_URL = 'http://localhost:8020';

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
