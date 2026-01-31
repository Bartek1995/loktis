// src/router/index.ts

/// <reference types="vite/client" />

import type { RouteRecordRaw } from 'vue-router';
import { createRouter, createWebHistory } from 'vue-router';

const routes: Array<RouteRecordRaw> = [
    {
        path: '/',
        name: 'landing',
        component: () => import('@/views/analyzer/LandingView.vue'),
        meta: { title: 'Analizator Ogłoszeń' }
    },
    {
        path: '/home',
        name: 'home',
        component: () => import('@/pages/HomePage.vue'),
        meta: { title: 'Analizator Ogłoszeń' }
    },
    {
        path: '/report',
        name: 'report',
        component: () => import('@/views/analyzer/ReportView.vue'),
        meta: { title: 'Raport analizy' }
    },
    {
        path: '/r/:publicId',
        name: 'report-public',
        component: () => import('@/views/analyzer/ReportView.vue'),
        meta: { title: 'Raport analizy' }
    },
    {
        path: '/history/:id',
        name: 'history-detail',
        component: () => import('@/views/analyzer/ReportView.vue'),
        meta: { title: 'Raport analizy' }
    },
    // Auth routes (tymczasowo nieaktywne, przygotowane na przyszłość)
    // {
    //     path: '/auth/login',
    //     name: 'login',
    //     component: () => import('@/views/auth/LoginView.vue'),
    //     meta: { title: 'Logowanie' }
    // },
    {
        path: '/:pathMatch(.*)*',
        name: 'not-found',
        component: () => import('@/views/NotFoundView.vue'),
        meta: { title: '404' }
    }
];

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes
});

// Update page title
router.beforeEach((to, _from, next) => {
    document.title = (to.meta.title as string) || 'Loktis - Analizator Ogłoszeń';
    next();
});

// TODO: Odkomentuj gdy auth będzie aktywne
// router.beforeEach(async (to) => {
//     const auth = useAuthStore();
//     if (!auth.isAuthReady) await auth.initialize();
//
//     if (to.meta.requiresAuth && !auth.isLoggedIn) {
//         return { name: 'login', query: { next: to.fullPath } };
//     }
//     if (to.name === 'login' && auth.isLoggedIn) {
//         return { name: 'landing', replace: true };
//     }
// });

export default router;
