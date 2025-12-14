import React, { useEffect, useState } from 'react';
import { getUserProfile, linkTelegram, unlinkTelegram } from '../services/api';
import { UserProfile } from '../types';

const ProfileView: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [telegramInput, setTelegramInput] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const data = await getUserProfile();
        setProfile(data);
      } catch (err) {
        setError('Не удалось загрузить профиль');
      } finally {
        setLoading(false);
      }
    };
    fetchProfile();
  }, []);

  const handleLinkTelegram = async () => {
    if (!telegramInput.trim()) {
      setError('Введите имя пользователя Telegram');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await linkTelegram(telegramInput.trim());
      setProfile(updated);
      setTelegramInput('');
    } catch (err) {
      setError('Не удалось привязать Telegram');
    } finally {
      setSaving(false);
    }
  };

  const handleUnlinkTelegram = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await unlinkTelegram();
      setProfile(updated);
    } catch (err) {
      setError('Не удалось отвязать Telegram');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-gray-300">Загрузка профиля...</div>;
  }

  if (error) {
    return <div className="p-6 text-red-400">{error}</div>;
  }

  if (!profile) {
    return <div className="p-6 text-gray-300">Профиль недоступен.</div>;
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <div className="bg-gray-800 rounded-lg p-6 shadow-md border border-gray-700">
        <h2 className="text-xl font-semibold text-white mb-4">Основная информация</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-gray-200">
          <div>
            <p className="text-sm text-gray-400">Имя</p>
            <p className="text-lg font-medium">{profile.name}</p>
          </div>
          <div>
            <p className="text-sm text-gray-400">Email</p>
            <p className="text-lg font-medium">{profile.email}</p>
          </div>
          <div>
            <p className="text-sm text-gray-400">Организация</p>
            <p className="text-lg font-medium">{profile.organization}</p>
          </div>
          <div>
            <p className="text-sm text-gray-400">Роль</p>
            <span className="inline-flex px-3 py-1 rounded-full bg-teal-900 text-teal-100 text-sm font-semibold">
              {profile.role}
            </span>
          </div>
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-6 shadow-md border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Telegram</h2>
          {profile.telegramUsername ? (
            <span className="text-sm text-green-300">Привязан</span>
          ) : (
            <span className="text-sm text-gray-400">Не привязан</span>
          )}
        </div>
        {profile.telegramUsername ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-gray-200">
              <span className="bg-green-900 text-green-100 px-3 py-1 rounded-full text-sm">
                {profile.telegramUsername}
              </span>
              <p className="text-gray-400">Уведомления будут приходить в этот аккаунт.</p>
            </div>
            <button
              onClick={handleUnlinkTelegram}
              disabled={saving}
              className="bg-red-700 hover:bg-red-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white px-4 py-2 rounded-md transition-colors"
            >
              Отключить Telegram
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <label className="block text-sm text-gray-300">Имя пользователя Telegram</label>
            <input
              type="text"
              value={telegramInput}
              onChange={(e) => setTelegramInput(e.target.value)}
              placeholder="@username"
              className="w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
            <div className="flex flex-wrap gap-3 items-center">
              <button
                onClick={handleLinkTelegram}
                disabled={saving}
                className="bg-teal-600 hover:bg-teal-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white px-4 py-2 rounded-md transition-colors"
              >
                Привязать Telegram
              </button>
              <p className="text-sm text-gray-400">Получайте уведомления о готовности ответов прямо в мессенджер.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ProfileView;
