import * as XLSX from 'xlsx';
import type { Config } from '@/types/core/CustomDataTable';

export async function exportToExcelNative(fetchData: () => Promise<Record<string, any>[]>, selectedColumns: Config[], filename = 'export.xlsx'): Promise<void> {
    try {
        // Pobierz dane
        const data = await fetchData();
        console.log('Dane do eksportu:', data);
        console.log('Wybrane kolumny:', selectedColumns);

        if (!data || data.length === 0) {
            console.warn('Brak danych do eksportu.');
            return;
        }

        // Filtrowanie danych wg wybranych kolumn (header jako nazwa kolumny w excelu)
        const filteredData = data.map((row) => {
            const filteredRow: Record<string, any> = {};
            selectedColumns.forEach((col) => {
                filteredRow[col.header] = row[col.field];
            });
            return filteredRow;
        });

        // Konwersja na arkusz Excel
        const worksheet = XLSX.utils.json_to_sheet(filteredData);
        const workbook = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(workbook, worksheet, 'Dane');

        // Zapis do pliku (w postaci blob)
        const wbout = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
        const blob = new Blob([wbout], {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        });

        // Tworzymy link do pobrania i klikamy go programowo
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();

        // Zwolnienie URL obiektu
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Błąd eksportu do Excela:', error);
        throw error; // opcjonalnie rzuć dalej, żeby komponent mógł zareagować
    }
}
