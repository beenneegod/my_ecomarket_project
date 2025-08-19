document.addEventListener('DOMContentLoaded', function() {
    console.log("Simplified Cart JS loaded");
    
    // Get CSRF token from cookie
    function getCSRFToken() {
        const cookieName = 'csrftoken';
        let cookieValue = null;
        
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, cookieName.length + 1) === (cookieName + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(cookieName.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    
    // Add to cart function with reliable CSRF handling
    function addToCart(btn, url, quantity) {
        // Show loading state
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Dodawanie...';
        
        // Find the closest form
        const form = btn.closest('form');
        if (!form) {
            console.error("Form not found");
            btn.innerHTML = originalText;
            btn.disabled = false;
            return;
        }
        
        // Set quantity in the form
        const quantityInput = form.querySelector('input[name="quantity"]');
        if (quantityInput) {
            quantityInput.value = quantity;
        }
        
        // Get CSRF token and add it to form if needed
        const token = getCSRFToken();
        let csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
        if (!csrfInput && token) {
            csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = token;
            form.appendChild(csrfInput);
        }
        
        // Create a hidden iframe for submission
        const iframeId = 'cart-submit-iframe';
        let iframe = document.getElementById(iframeId);
        
        if (!iframe) {
            iframe = document.createElement('iframe');
            iframe.id = iframeId;
            iframe.name = iframeId;
            iframe.style.display = 'none';
            document.body.appendChild(iframe);
        }
        
        // Save original form attributes
        const originalAction = form.action;
        const originalTarget = form.target;
        const originalMethod = form.method;
        
        // Set up form for submission
        form.action = url;
        form.target = iframeId;
        form.method = 'post';
        
        // Set up callback for iframe load
        iframe.onload = function() {
            // Reset form
            form.action = originalAction;
            form.target = originalTarget;
            form.method = originalMethod;
            
            // Get updated cart count
            setTimeout(function() {
                fetch('/store/cart/count/', {
                    method: 'GET',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                .then(function(response) {
                    return response.json();
                })
                .then(function(data) {
                    const cartCountElement = document.getElementById('cart-count');
                    if (cartCountElement && data.count !== undefined) {
                        cartCountElement.textContent = data.count;
                        
                        // Animate cart icon
                        const cartLink = document.getElementById('cart-link');
                        if (cartLink) {
                            cartLink.classList.remove('animate-pop');
                            setTimeout(function() {
                                cartLink.classList.add('animate-pop');
                            }, 10);
                        }
                    }
                })
                .catch(function(error) {
                    console.error("Błąd aktualizacji liczby produktów w koszyku:", error);
                });
                
                // Show success on button
                btn.innerHTML = '<i class="bi bi-check-lg"></i> Dodano!';
                setTimeout(function() {
                    btn.innerHTML = originalText;
                    btn.disabled = false;
                }, 1500);
            }, 500); // Small delay to ensure server processing completes
        };
        
        // Submit the form
        form.submit();
    }
    
    // Attach click handlers to add-to-cart buttons
    document.querySelectorAll('.add-to-cart-btn').forEach(function(button) {
        button.addEventListener('click', function(event) {
            const btn = event.currentTarget;
            const url = btn.dataset.addUrl;
            
            // Get quantity from input or default to 1
            let quantity = 1;
            const formContainer = btn.closest('.add-to-cart-form');
            if (formContainer) {
                const quantityInput = formContainer.querySelector('input[name="quantity"]');
                if (quantityInput) {
                    quantity = parseInt(quantityInput.value) || 1;
                }
            }
            
            addToCart(btn, url, quantity);
        });
    });
});
