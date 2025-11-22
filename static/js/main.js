// ZedinArkManager - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
    
    // Form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const passwordInputs = form.querySelectorAll('input[type="password"]');
            if (passwordInputs.length === 2) {
                const password = passwordInputs[0].value;
                const passwordConfirm = passwordInputs[1].value;
                
                if (password !== passwordConfirm) {
                    e.preventDefault();
                    alert('A jelszavak nem egyeznek!');
                    return false;
                }
            }
        });
    });
});

