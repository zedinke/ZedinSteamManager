// ZedinArkManager - Main JavaScript

// Theme Management
function initTheme() {
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    const html = document.documentElement;
    
    // Load saved theme or default to light
    const savedTheme = localStorage.getItem('theme') || 'light';
    html.setAttribute('data-theme', savedTheme);
    
    // Update icon
    if (themeIcon) {
        themeIcon.className = savedTheme === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
    }
    
    // Toggle theme on button click
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            
            if (themeIcon) {
                themeIcon.className = newTheme === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
            }
        });
    }
}

// Mobile Menu Toggle
function initMobileMenu() {
    const mobileMenuToggle = document.getElementById('mobileMenuToggle');
    const sidebar = document.querySelector('.sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    
    if (mobileMenuToggle && sidebar) {
        mobileMenuToggle.addEventListener('click', function() {
            sidebar.classList.toggle('open');
            if (sidebarOverlay) {
                sidebarOverlay.classList.toggle('active');
            }
        });
        
        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', function() {
                sidebar.classList.remove('open');
                sidebarOverlay.classList.remove('active');
            });
        }
        
        // Close sidebar when clicking on a nav item (mobile)
        const navItems = sidebar.querySelectorAll('.nav-item');
        navItems.forEach(item => {
            item.addEventListener('click', function() {
                if (window.innerWidth <= 768) {
                    sidebar.classList.remove('open');
                    if (sidebarOverlay) {
                        sidebarOverlay.classList.remove('active');
                    }
                }
            });
        });
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Initialize theme
    initTheme();
    
    // Initialize mobile menu
    initMobileMenu();
    
    // Auto-hide alerts disabled - alerts will remain visible until manually closed
    // (Commented out to keep alert messages visible)
    // const alerts = document.querySelectorAll('.alert');
    // alerts.forEach(alert => {
    //     setTimeout(() => {
    //         alert.style.opacity = '0';
    //         setTimeout(() => alert.remove(), 300);
    //     }, 5000);
    // });
    
    // Form validation - csak akkor ellenőrizzük, ha a mezők nevei azt jelzik, hogy megerősítő mezők
    // (pl. password és password_confirm, nem pedig server_admin_password és server_password)
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const passwordInputs = form.querySelectorAll('input[type="password"]');
            if (passwordInputs.length === 2) {
                const password1 = passwordInputs[0];
                const password2 = passwordInputs[1];
                
                // Csak akkor ellenőrizzük, ha a mezők nevei azt jelzik, hogy megerősítő mezők
                // (pl. "password" és "password_confirm", nem pedig "server_admin_password" és "server_password")
                const name1 = password1.name || password1.id || '';
                const name2 = password2.name || password2.id || '';
                
                // Ha a mezők nevei tartalmaznak "confirm" vagy "password" és "password_confirm" páros,
                // akkor ellenőrizzük az egyezést
                const isPasswordConfirm = (
                    (name1.includes('password') && name2.includes('confirm')) ||
                    (name2.includes('password') && name1.includes('confirm')) ||
                    (name1 === 'password' && name2 === 'password_confirm') ||
                    (name1 === 'password_confirm' && name2 === 'password') ||
                    (name1 === 'new_password' && name2 === 'confirm_password') ||
                    (name1 === 'confirm_password' && name2 === 'new_password')
                );
                
                // Ha NEM megerősítő mezők (pl. server_admin_password és server_password), akkor NEM ellenőrizzük
                if (!isPasswordConfirm) {
                    return; // Két különböző jelszó mező, nem kell ellenőrizni
                }
                
                // Megerősítő mezők esetén ellenőrizzük az egyezést
                if (password1.value !== password2.value) {
                    e.preventDefault();
                    alert('A jelszavak nem egyeznek!');
                    return false;
                }
            }
        });
    });
});

