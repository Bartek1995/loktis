<script setup lang="ts">
import { ref } from 'vue';

import AppMenuItem from './AppMenuItem.vue';

const model = ref([
    {
        label: 'Mieszkania',
        items: [
            { label: 'Lista mieszkan', icon: 'pi pi-fw pi-building', to: '/' },
            { label: 'Rzuty', icon: 'pi pi-fw pi-image', to: '/layouts' }
        ]
    },
    {
        label: 'Narzedzia',
        items: [
            { label: 'Diagnostyka', icon: 'pi pi-fw pi-wrench', to: '/diagnostics' },
            { label: 'Debug', icon: 'pi pi-fw pi-bug', to: '/debug' }
        ]
    },
    {
        label: 'System',
        items: [
            { label: 'Ustawienia', icon: 'pi pi-fw pi-cog', to: '/settings' }
        ]
    }
]);
</script>

<template>
    <ul class="layout-menu">
        <template v-for="(item, i) in model" :key="i">
            <app-menu-item v-if="!('separator' in item)" :item="item" :index="i"></app-menu-item>
            <li v-if="'separator' in item" class="menu-separator"></li>
        </template>
    </ul>
</template>

<style lang="scss" scoped></style>
