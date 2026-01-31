// src/api/apiService.ts

import axios from 'axios';
import router from '@/router';
import { useAuthStore } from '@/stores/auth';
import { useLanguageStore } from '@/stores/language';

const api = axios.create({
    baseURL: '/api'
});

let isRefreshing = false;
let failedQueue: Array<{ resolve: (value: any) => void; reject: (reason?: any) => void }> = [];

const processQueue = (error: any, token: string | null = null) => {
    failedQueue.forEach((prom) => {
        if (error) {
            prom.reject(error);
        } else {
            prom.resolve(token);
        }
    });
    failedQueue = [];
};

// Interceptor do ustawiania nagłówków z językiem i tokenem
api.interceptors.request.use((config) => {
    const langStore = useLanguageStore();
    const auth = useAuthStore();

    config.headers = config.headers || {};
    config.headers['Accept-Language'] = langStore.selected;

    if (auth.accessToken) {
        config.headers['Authorization'] = `Bearer ${auth.accessToken}`;
    }

    return config;
});

// Interceptor do obsługi automatycznego odświeżania JWT po 401
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;
        const auth = useAuthStore();

        if (error.response?.status === 401 && !originalRequest._retry) {
            if (isRefreshing) {
                // Jeśli odświeżanie już trwa, dodaj żądanie do kolejki
                return new Promise((resolve, reject) => {
                    failedQueue.push({ resolve, reject });
                }).then((token) => {
                    originalRequest.headers['Authorization'] = 'Bearer ' + token;
                    return api(originalRequest);
                });
            }

            originalRequest._retry = true;
            isRefreshing = true;

            try {
                const refreshToken = auth.refreshToken;
                if (!refreshToken) {
                    throw new Error('No refresh token available');
                }

                const { data } = await axios.post('http://localhost:8000/api/v1/auth/token/refresh/', {
                    refresh: refreshToken
                });

                auth.accessToken = data.access;
                if (data.refresh) {
                    auth.refreshToken = data.refresh;
                }
                api.defaults.headers.common['Authorization'] = `Bearer ${data.access}`;

                processQueue(null, data.access);

                originalRequest.headers['Authorization'] = `Bearer ${data.access}`;
                return api(originalRequest);
            } catch (refreshError) {
                processQueue(refreshError, null);
                auth.logout();
                router.push({ name: 'login' });
                console.log('Session expired, redirecting to login', refreshError);
                return Promise.reject(refreshError);
            } finally {
                isRefreshing = false;
            }
        }

        return Promise.reject(error);
    }
);

export default api;
