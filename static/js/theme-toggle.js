document.addEventListener('DOMContentLoaded', function() {
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const root = document.documentElement;
    const storedTheme = localStorage.getItem('theme');
    
    // Set initial theme based on stored preference or system preference
    if (storedTheme === 'dark') {
        root.classList.add('dark-mode');
        updateThemeIcon(true);
    } else if (storedTheme === 'light') {
        root.classList.add('light-mode');
        updateThemeIcon(false);
    } else {
        // Check system preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            root.classList.add('dark-mode');
            updateThemeIcon(true);
        } else {
            updateThemeIcon(false);
        }
    }
    
    // Toggle theme on button click or keyboard (Enter/Space)
    const toggleTheme = () => {
        const isDarkMode = root.classList.contains('dark-mode');
        if (isDarkMode) {
            root.classList.remove('dark-mode');
            root.classList.add('light-mode');
            localStorage.setItem('theme', 'light');
            updateThemeIcon(false);
            themeToggleBtn.setAttribute('aria-pressed', 'false');
        } else {
            root.classList.remove('light-mode');
            root.classList.add('dark-mode');
            localStorage.setItem('theme', 'dark');
            updateThemeIcon(true);
            themeToggleBtn.setAttribute('aria-pressed', 'true');
        }
    };
    themeToggleBtn.addEventListener('click', toggleTheme);
    themeToggleBtn.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleTheme(); }
    });
    
    // Update icon based on current theme
    function updateThemeIcon(isDarkMode) {
        const iconElement = themeToggleBtn.querySelector('i');
        if (isDarkMode) {
            iconElement.className = 'bi bi-sun-fill';
            themeToggleBtn.setAttribute('title', 'Przełącz na tryb jasny');
            themeToggleBtn.setAttribute('aria-label', 'Przełącz na tryb jasny');
            themeToggleBtn.setAttribute('aria-pressed', 'true');
        } else {
            iconElement.className = 'bi bi-moon-fill';
            themeToggleBtn.setAttribute('title', 'Przełącz na tryb ciemny');
            themeToggleBtn.setAttribute('aria-label', 'Przełącz na tryb ciemny');
            themeToggleBtn.setAttribute('aria-pressed', 'false');
        }
    }
});
