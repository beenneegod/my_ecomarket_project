function initCartInteractions() {
    console.log("Cart JS loaded");

    // Global toggle to disable Toastify pop-ups across cart interactions
    const SHOW_CART_TOASTS = false;
    if (!SHOW_CART_TOASTS) {
        // Replace Toastify with a no-op stub to avoid UI popups while keeping calls harmless
        window.Toastify = function () {
            return { showToast() {} };
        };
    }

    // --- CSRF helpers ---
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    function getCsrfTokenFromElement(el) {
        const form = el && el.closest ? el.closest('form') : null;
        if (form) {
            const input = form.querySelector('input[name="csrfmiddlewaretoken"]');
            if (input && input.value) return input.value;
        }
        const anyInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (anyInput && anyInput.value) return anyInput.value;
        // Fallback (works only if CSRF_COOKIE_HTTPONLY is False)
        return getCookie('csrftoken');
    }

    // --- Обновление счетчика корзины в шапке ---
    function updateCartCount(newCount) {
        const cartCountElement = document.getElementById('cart-count');
        if (!cartCountElement) return;

        const prev = parseInt(cartCountElement.textContent) || 0;
        cartCountElement.textContent = newCount;

        const cartLinkElement = cartCountElement.closest('a');
        if (!cartLinkElement) return;

        // Анимируем только когда количество растет, чтобы не мигать при удалении
        if (newCount > prev) {
            cartLinkElement.classList.remove('animate-pop');
            // Мини-дебаунс на один кадр, чтобы класс успел сняться
            requestAnimationFrame(() => {
                cartLinkElement.classList.add('animate-pop');
                setTimeout(() => {
                    cartLinkElement.classList.remove('animate-pop');
                }, 220);
            });
        }
    }

    // Update summary prices (full price, discount, total to pay) and keep currency PLN
    function updateSummaryPrices({ cart_total_price, cart_total_price_after_discount, cart_discount_amount }) {
        const fullPriceEl = document.getElementById('cart-full-price');
        if (fullPriceEl && typeof cart_total_price !== 'undefined') {
            fullPriceEl.textContent = `${cart_total_price} PLN`;
        }

        const totalPayEl = document.getElementById('cart-total-price');
        if (totalPayEl && typeof cart_total_price_after_discount !== 'undefined') {
            totalPayEl.textContent = `${cart_total_price_after_discount} PLN`;
        }

        const discountEl = document.getElementById('cart-discount-amount');
        if (discountEl && typeof cart_discount_amount !== 'undefined') {
            discountEl.textContent = `-${cart_discount_amount} PLN`;
        }
    }

    // --- Надёжное удаление строки товара по productId ---
    function removeCartRowById(productId) {
        const pid = String(productId);
        const selector = (window.CSS && CSS.escape) ? `.cart-item[data-product-id="${CSS.escape(pid)}"]` : `.cart-item[data-product-id="${pid}"]`;
        const row = document.querySelector(selector);
        if (row) {
            row.remove();
            return true;
        }
        return false;
    }

    // --- Функция для фактического выполнения AJAX-запроса на удаление ---
    function performDeleteRequest(productId, url, cartItemRow, currentButton) {
        const token = getCsrfTokenFromElement(cartItemRow || document.body);
        if (currentButton) currentButton.disabled = true;
        const formData = new URLSearchParams();
        if (token) {
            formData.append('csrfmiddlewaretoken', token);
        }

        fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': token || '',
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            credentials: 'same-origin',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                return response.json().catch(() => ({})).then(err => {
                    throw new Error(err.error || `HTTP error! status: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'ok') {
                console.log(`Product ${productId} removed from cart.`);
                if (cartItemRow) {
                    cartItemRow.remove();
                } else {
                    removeCartRowById(productId);
                }
                updateCartCount(data.cart_total_items);
                updateSummaryPrices({
                    cart_total_price: data.cart_total_price,
                    cart_total_price_after_discount: data.cart_total_price_after_discount,
                    cart_discount_amount: data.cart_discount_amount,
                });
                if (data.cart_total_items === 0) {
                    setTimeout(() => { window.location.reload(); }, 500);
                }
                if (window.Swal && typeof Swal.fire === 'function') {
                    Swal.fire({
                        icon: 'success',
                        title: 'Usunięto z koszyka',
                        text: 'Produkt usunięty z koszyka.',
                        position: 'center',
                        showConfirmButton: false,
                        timer: 1500,
                        timerProgressBar: true,
                    });
                } else if (SHOW_CART_TOASTS && window.Toastify) {
                    Toastify({
                        text: "Produkt usunięty z koszyka.",
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        style: { background: "linear-gradient(to right, #00b09b, #96c93d)" }
                    }).showToast();
                } else {
                    alert('Produkt usunięty z koszyka.');
                }
            } else {
                console.error("Błąd usuwania produktu:", data && data.error ? data.error : 'Nieznany błąd serwera');
                // Fallback: optimistically remove row and refresh key UI parts
                if (!removeCartRowById(productId) && cartItemRow) {
                    try { cartItemRow.remove(); } catch (_) {}
                }
                // If cart becomes empty or unknown state, do a light reload to sync UI
                setTimeout(() => { window.location.reload(); }, 250);
                if (currentButton) currentButton.disabled = false;
            }
        })
        .catch(error => {
            console.error('Fetch Error during delete:', error);
            if (window.Swal && typeof Swal.fire === 'function') {
                Swal.fire({
                    icon: 'error',
                    title: 'Błąd',
                    text: 'Wystąpił błąd podczas usuwania produktu. Spróbuj ponownie.',
                    position: 'center',
                    showConfirmButton: false,
                    timer: 1800,
                    timerProgressBar: true,
                });
            } else if (SHOW_CART_TOASTS && window.Toastify) {
                Toastify({
                    text: 'Wystąpił błąd podczas usuwania produktu. Spróbuj ponownie.',
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" }
                }).showToast();
            } else {
                alert('Wystąpił błąd podczas usuwania produktu. Spróbuj ponownie.');
            }
            if (currentButton) currentButton.disabled = false;
        });
    }

    // --- Обработка кнопки "Добавить в корзину" (УНИВЕРСАЛЬНАЯ) ---
    document.querySelectorAll('.add-to-cart-btn').forEach(button => {
        button.addEventListener('click', event => {
            const btn = event.target.closest('.add-to-cart-btn');
            if (!btn) return;

            const productId = btn.dataset.productId;
            const url = btn.dataset.addUrl;

            const formContainer = btn.closest('.add-to-cart-form');
            let quantityInput = null;
            if (formContainer) {
                quantityInput = formContainer.querySelector('.quantity-input-detail, input[name="quantity"]');
            }

            const quantity = quantityInput ? parseInt(quantityInput.value) : 1;

            if (isNaN(quantity) || quantity <= 0) {
                Toastify({
                    text: 'Proszę wprowadzić poprawną ilość (więcej niż 0).',
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" }
                }).showToast();
                return;
            }

            if (quantityInput && quantityInput.max && quantity > parseInt(quantityInput.max)) {
                Toastify({
                    text: `Przepraszamy, dostępnych jest tylko ${quantityInput.max} szt.`,
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" }
                }).showToast();
                return;
            }

            const token = getCsrfTokenFromElement(btn);
            const formData = new URLSearchParams();
            formData.append('quantity', quantity);
            if (token) {
                formData.append('csrfmiddlewaretoken', token);
            }

            btn.disabled = true;
            const originalButtonContent = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Dodawanie...';

            fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': token || '',
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(errData => {
                        throw new Error(errData.error || `HTTP error! status: ${response.status}`);
                    }).catch(() => {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'ok') {
                    updateCartCount(data.cart_total_items);
                    console.log(`Product ${productId} added/updated in cart (quantity: ${quantity}).`);
                    updateSummaryPrices({
                        cart_total_price: data.cart_total_price,
                        cart_total_price_after_discount: data.cart_total_price_after_discount,
                        cart_discount_amount: data.cart_discount_amount,
                    });
                    Toastify({
                        text: "Produkt dodany do koszyka!",
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        style: { background: "linear-gradient(to right, #00b09b, #96c93d)" }
                    }).showToast();

                    btn.classList.add('is-success');
                    btn.innerHTML = '<i class="bi bi-check-lg"></i> Dodano!';

                    setTimeout(() => {
                        btn.classList.remove('is-success');
                        btn.innerHTML = originalButtonContent;
                        btn.disabled = false;
                    }, 2000);

                    if (data.quantity_adjusted && quantityInput) {
                        quantityInput.value = data.adjusted_quantity;
                        Toastify({
                            text: `Ilość produktu "${data.product_name}" skorygowana do ${data.adjusted_quantity} szt. (Maksymalna ilość na stanie).`,
                            duration: 5000,
                            gravity: "top",
                            position: "right",
                            style: { background: "linear-gradient(to right, #ff8c00, #ffc371)" } // ИСПРАВЛЕНО (в твоем коде уже было style, но на всякий случай)
                        }).showToast();
                    }
                } else {
                    console.error("Błąd dodawania produktu:", data.error || 'Nieznany błąd serwera');
                    Toastify({
                        text: `Nie udało się dodać produktu: ${data.error || 'Błąd serwera'}`,
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" } // ИСПРАВЛЕНО
                    }).showToast();
                    btn.innerHTML = originalButtonContent;
                    btn.disabled = false;
                }
            })
            .catch(error => {
                console.error('Fetch Error:', error);
                Toastify({
                    text: `Błąd przy dodawaniu produktu: ${error.message}`, // Текст был на русском, заменил
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" }
                }).showToast();
                btn.innerHTML = originalButtonContent;
                btn.disabled = false;
            });
        });
    });

    // --- Обработка кнопки "Удалить" (на странице корзины) с SweetAlert2 ---
    document.querySelectorAll('.remove-from-cart-btn').forEach(button => {
        button.addEventListener('click', event => {
            const currentButton = event.target.closest('.remove-from-cart-btn');
            if (!currentButton) { return; }
            const productId = currentButton.dataset.productId;
            const removeUrl = currentButton.dataset.removeUrl;
            const cartItemRow = currentButton.closest('.cart-item');

            if (!productId || !removeUrl) {
                console.error("Product ID is undefined for remove button:", currentButton);
                Toastify({
                    text: "Nie udało się określić ID produktu do usunięcia.",
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" }
                }).showToast();
                return;
            }

            if (window.Swal && typeof Swal.fire === 'function') {
                Swal.fire({
                    title: 'Potwierdź usunięcie',
                    text: "Czy na pewno chcesz usunąć ten produkt z koszyka?",
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonText: 'Tak, usuń',
                    cancelButtonText: 'Anuluj',
                    confirmButtonColor: 'var(--color-primary)',
                    cancelButtonColor: 'var(--color-text-medium)',
                }).then((result) => {
                    if (result.isConfirmed) {
                        performDeleteRequest(productId, removeUrl, cartItemRow, currentButton);
                    }
                });
            } else {
                if (window.confirm("Czy na pewno chcesz usunąć ten produkt z koszyka?")) {
                    performDeleteRequest(productId, removeUrl, cartItemRow, currentButton);
                }
            }
        });
    });

    // --- Обработка изменения количества в input .quantity-input (на странице корзины) ---
    document.querySelectorAll('.quantity-input').forEach(input => {
        input.addEventListener('change', event => {
            const productId = event.target.dataset.productId;
            const newQuantity = parseInt(event.target.value);
            const url = event.target.dataset.updateUrl;
            const cartItemRow = event.target.closest('.cart-item');

            if (isNaN(newQuantity) || newQuantity < 0) {
                Toastify({
                    text: 'Proszę wprowadzić poprawną ilość.',
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" } // ИСПРАВЛЕНО
                }).showToast();
                // Можно добавить логику восстановления предыдущего значения инпута, если есть
                // event.target.value = event.target.defaultValue; // или сохраненное ранее значение
                return;
            }

            const token = getCsrfTokenFromElement(event.target);
            const formData = new URLSearchParams();
            formData.append('quantity', newQuantity);
            formData.append('update', 'true');
            if (token) {
                formData.append('csrfmiddlewaretoken', token);
            }

            fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': token || '',
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(errData => {
                        throw new Error(errData.error || `HTTP error! status: ${response.status}`);
                    }).catch(() => {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'ok') {
                    console.log(`Product ${productId} quantity updated to ${newQuantity}.`);

                    const itemTotalPriceElement = cartItemRow.querySelector('.item-total-price');
                    if (itemTotalPriceElement) {
                        itemTotalPriceElement.textContent = `${data.item_total_price} PLN`;
                    }

                    updateSummaryPrices({
                        cart_total_price: data.cart_total_price,
                        cart_total_price_after_discount: data.cart_total_price_after_discount,
                        cart_discount_amount: data.cart_discount_amount,
                    });

                    updateCartCount(data.cart_total_items);

                    if (data.item_removed) {
                        if (cartItemRow) {
                            cartItemRow.remove();
                        } else {
                            removeCartRowById(productId);
                        }
                        if (data.cart_total_items === 0) {
                            setTimeout(() => { window.location.reload(); }, 500);
                        }
                        if (window.Swal && typeof Swal.fire === 'function') {
                            Swal.fire({
                                icon: 'success',
                                title: 'Usunięto z koszyka',
                                text: 'Produkt usunięty (Ilość 0).',
                                position: 'center',
                                showConfirmButton: false,
                                timer: 1500,
                                timerProgressBar: true,
                            });
                        } else if (SHOW_CART_TOASTS && window.Toastify) {
                            Toastify({
                                text: "Produkt usunięty (Ilość 0).",
                                duration: 3000,
                                gravity: "top",
                                position: "right",
                                style: { background: "linear-gradient(to right, #00b09b, #96c93d)" }
                            }).showToast();
                        } else {
                            alert('Produkt usunięty (Ilość 0).');
                        }

                    } else if (data.quantity_adjusted) {
                        event.target.value = data.adjusted_quantity;
                        Toastify({
                            text: `Ilość produktu "${data.product_name}" poprawiona do ${data.adjusted_quantity} szt. (maksymalna ilość na stanie).`,
                            duration: 5000,
                            gravity: "top",
                            position: "right",
                            style: { background: "linear-gradient(to right, #ff8c00, #ffc371)" }
                        }).showToast();
                    } else {
                        Toastify({
                            text: "Ilość zaktualizowana.",
                            duration: 3000,
                            gravity: "top",
                            position: "right",
                            style: { background: "linear-gradient(to right, #00b09b, #96c93d)" }
                        }).showToast();
                    }
                } else {
                    console.error("Błąd aktualizacji ilości:", data.error || 'Nieznany błąd serwera');
                    Toastify({
                        text: `Nie udało się zaktualizować ilości: ${data.error || 'Błąd serwera'}`,
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" }
                    }).showToast();
                }
            })
            .catch(error => {
                console.error('Błąd żądania podczas aktualizacji ilości:', error);
                Toastify({
                    text: `Błąd przy aktualizacji ilości: ${error.message}`,
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" } // ИСПРАВЛЕНО
                }).showToast();
            });
        });
    });

}

// Initialize immediately if DOM is ready, otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCartInteractions);
} else {
    initCartInteractions();
}