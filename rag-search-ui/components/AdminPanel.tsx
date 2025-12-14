import React, { useEffect, useMemo, useState } from 'react';
import {
  createEmailInvite,
  createLinkInvite,
  getInvites,
  getUsers,
  resetPassword,
  resetTwoFactor,
  updateUserRole,
} from '../services/api';
import { AdminUser, Invite, UserRole } from '../types';

const roleLabels: Record<UserRole, string> = {
  admin: 'Администратор',
  editor: 'Редактор',
  viewer: 'Читатель',
};

const AdminPanel: React.FC = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [usersData, inviteData] = await Promise.all([getUsers(), getInvites()]);
        setUsers(usersData);
        setInvites(inviteData);
      } catch (err) {
        setError('Не удалось загрузить данные администратора');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const handleRoleChange = async (userId: string, role: UserRole) => {
    setMessage(null);
    try {
      const updated = await updateUserRole(userId, role);
      setUsers(prev => prev.map(user => user.id === userId ? updated : user));
      setMessage('Роль обновлена');
    } catch (err) {
      setError('Не удалось обновить роль');
    }
  };

  const handleResetPassword = async (userId: string) => {
    setMessage(null);
    await resetPassword(userId);
    setMessage('Ссылка для сброса пароля отправлена');
  };

  const handleReset2FA = async (userId: string) => {
    setMessage(null);
    await resetTwoFactor(userId);
    setMessage('2FA сброшена для пользователя');
  };

  const handleInviteEmail = async () => {
    if (!inviteEmail.trim()) {
      setError('Введите email для приглашения');
      return;
    }
    setCreatingInvite(true);
    setError(null);
    try {
      const invite = await createEmailInvite(inviteEmail.trim(), 'admin');
      setInvites(prev => [invite, ...prev]);
      setInviteEmail('');
      setMessage('Приглашение отправлено на email');
    } catch (err) {
      setError('Не удалось отправить приглашение');
    } finally {
      setCreatingInvite(false);
    }
  };

  const handleInviteLink = async () => {
    setCreatingInvite(true);
    setError(null);
    try {
      const invite = await createLinkInvite('admin');
      setInvites(prev => [invite, ...prev]);
      setMessage('Сгенерирована новая ссылка приглашения');
    } catch (err) {
      setError('Не удалось создать ссылку');
    } finally {
      setCreatingInvite(false);
    }
  };

  const sortedInvites = useMemo(() => [...invites].sort((a, b) => b.createdAt.localeCompare(a.createdAt)), [invites]);

  if (loading) {
    return <div className="p-6 text-gray-300">Загрузка данных администратора...</div>;
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {(error || message) && (
        <div className={`p-3 rounded-md ${error ? 'bg-red-900/40 text-red-200' : 'bg-teal-900/40 text-teal-100'}`}>
          {error || message}
        </div>
      )}

      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 shadow-md">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold text-white">Пользователи</h2>
            <p className="text-sm text-gray-400">Назначение ролей и управление доступом</p>
          </div>
        </div>
        <div className="space-y-4">
          {users.map(user => (
            <div key={user.id} className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 bg-gray-900/50 rounded-lg p-4 border border-gray-700">
              <div>
                <p className="text-white font-medium">{user.name}</p>
                <p className="text-gray-400 text-sm">{user.email}</p>
                <p className="text-gray-400 text-sm">Организация: {user.organization}</p>
                <p className="text-xs text-gray-500">Последняя активность: {new Date(user.lastActivity).toLocaleString('ru-RU')}</p>
              </div>
              <div className="flex flex-col md:flex-row gap-2 md:items-center">
                <select
                  value={user.role}
                  onChange={(e) => handleRoleChange(user.id, e.target.value as UserRole)}
                  className="bg-gray-900 border border-gray-700 text-white rounded-md px-3 py-2"
                >
                  {Object.entries(roleLabels).map(([value, label]) => (
                    <option value={value} key={value}>{label}</option>
                  ))}
                </select>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => handleResetPassword(user.id)}
                    className="bg-blue-700 hover:bg-blue-600 text-white px-3 py-2 rounded-md text-sm"
                  >
                    Сброс пароля
                  </button>
                  <button
                    onClick={() => handleReset2FA(user.id)}
                    className="bg-orange-700 hover:bg-orange-600 text-white px-3 py-2 rounded-md text-sm"
                  >
                    Сбросить 2FA
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700 shadow-md">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold text-white">Приглашения</h2>
            <p className="text-sm text-gray-400">Отправка по email или создание ссылки</p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div className="space-y-2">
            <label className="text-sm text-gray-300">Пригласить по email</label>
            <div className="flex gap-2">
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="user@example.com"
                className="flex-1 bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
              <button
                onClick={handleInviteEmail}
                disabled={creatingInvite}
                className="bg-teal-600 hover:bg-teal-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white px-4 py-2 rounded-md"
              >
                Отправить
              </button>
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-gray-300">Пригласить по ссылке</label>
            <button
              onClick={handleInviteLink}
              disabled={creatingInvite}
              className="w-full bg-indigo-700 hover:bg-indigo-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white px-4 py-2 rounded-md"
            >
              Сгенерировать ссылку
            </button>
          </div>
        </div>

        <div className="space-y-3">
          {sortedInvites.length === 0 ? (
            <p className="text-gray-400">Приглашений пока нет.</p>
          ) : (
            sortedInvites.map(invite => (
              <div key={invite.id} className="bg-gray-900/40 border border-gray-700 rounded-lg p-3 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div>
                  <p className="text-white font-medium">{invite.email || 'Приглашение по ссылке'}</p>
                  <p className="text-gray-400 text-sm break-all">{invite.link}</p>
                  <p className="text-xs text-gray-500">Создано: {new Date(invite.createdAt).toLocaleString('ru-RU')}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-3 py-1 rounded-full text-sm ${invite.status === 'pending' ? 'bg-yellow-900 text-yellow-100' : 'bg-green-900 text-green-100'}`}>
                    {invite.status === 'pending' ? 'Ожидает' : 'Принято'}
                  </span>
                  <span className="px-3 py-1 rounded-full text-sm bg-gray-700 text-gray-100">{invite.type === 'email' ? 'Email' : 'Ссылка'}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminPanel;
