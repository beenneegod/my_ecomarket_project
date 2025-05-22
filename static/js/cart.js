// static/js/cart.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("Cart JS loaded");

    // --- Функция получения CSRF токена ---
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
    const csrftoken = getCookie('csrftoken');

    // --- Обновление счетчика корзины в шапке ---
    function updateCartCount(newCount) {
        const cartCountElement = document.getElementById('cart-count');
        if (cartCountElement) {
            cartCountElement.textContent = newCount;
            const cartLinkElement = cartCountElement.closest('a');

            if (cartLinkElement) {
                cartLinkElement.classList.remove('animate-pop');
                requestAnimationFrame(() => {
                    cartLinkElement.classList.add('animate-pop');
                });
                setTimeout(() => {
                    cartLinkElement.classList.remove('animate-pop');
                }, 300);
            }
        }
    }

    // --- Функция для фактического выполнения AJAX-запроса на удаление ---
    function performDeleteRequest(productId, cartItemRow) {
        const url = `/store/cart/remove/${productId}/`;

        fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) {
                // Попробуем получить JSON с ошибкой от сервера
                return response.json().then(errData => {
                    throw new Error(errData.error || `HTTP error! status: ${response.status}`);
                }).catch(() => {
                    // Если JSON нет или он невалидный, бросаем общую ошибку
                    throw new Error(`HTTP error! status: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'ok') {
                console.log(`Product ${productId} removed from cart.`);
                if (cartItemRow) {
                    cartItemRow.classList.add('is-removing');
                    cartItemRow.addEventListener('transitionend', () => {
                        cartItemRow.remove();
                    }, { once: true });
                }
                updateCartCount(data.cart_total_items);
                const totalPriceElement = document.getElementById('cart-total-price');
                if (totalPriceElement) {
                    totalPriceElement.textContent = data.cart_total_price;
                }
                if (data.cart_total_items === 0) {
                    setTimeout(() => { window.location.reload(); }, 500);
                }
                Toastify({
                    text: "Produkt usunięty z koszyka.",
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #00b09b, #96c93d)" }
                }).showToast();
            } else {
                console.error("Error removing product:", data.error || 'Unknown server error');
                Toastify({
                    text: `Nie udało się usunąć produktu: ${data.error || 'Błąd serwera'}`,
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" }
                }).showToast();
            }
        })
        .catch(error => {
            console.error('Fetch Error during delete:', error);
            Toastify({
                text: `Błąd usunięcia produktu: ${error.message}`,
                duration: 3000,
                gravity: "top",
                position: "right",
                style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" }
            }).showToast();
        });
    }

    // --- Обработка кнопки "Добавить в корзину" (УНИВЕРСАЛЬНАЯ) ---
    document.querySelectorAll('.add-to-cart-btn').forEach(button => {
        button.addEventListener('click', event => {
            const btn = event.target.closest('.add-to-cart-btn');
            if (!btn) return;

            const productId = btn.dataset.productId;
            const url = `/store/cart/add/${productId}/`;

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
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" } // Исправлено backgroundColor
                }).showToast();
                return;
            }

            const formData = new URLSearchParams();
            formData.append('quantity', quantity);

            btn.disabled = true;
            const originalButtonContent = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Dodawanie...';

            fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken,
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: formData
            })
            .then(response => {
                // Возвращаем кнопку в активное состояние и исходное содержимое только после обработки ответа,
                // чтобы избежать двойного клика или если ошибка не JSON
                // btn.disabled = false; // Убрано отсюда
                // btn.innerHTML = originalButtonContent; // Убрано отсюда

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
                            style: { background: "linear-gradient(to right, #ff8c00, #ffc371)" } // Исправлено backgroundColor
                        }).showToast();
                    }
                } else {
                    console.error("Error adding product:", data.error || 'Unknown server error');
                    Toastify({
                        text: `Nie udało się dodać produktu: ${data.error || 'Błąd serwera'}`,
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" } // Исправлено backgroundColor
                    }).showToast();
                    btn.innerHTML = originalButtonContent; // Возвращаем исходный текст при ошибке
                    btn.disabled = false;
                }
            })
            .catch(error => {
                console.error('Fetch Error:', error);
                Toastify({
                    text: `Błąd przy dodawaniu produktu: ${error.message}`,
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" }
                }).showToast();
                btn.innerHTML = originalButtonContent; // Возвращаем исходный текст при ошибке
                btn.disabled = false;
            });
        });
    });

    // --- Обработка кнопки "Удалить" (на странице корзины) с SweetAlert2 ---
    document.querySelectorAll('.remove-from-cart-btn').forEach(button => {
        button.addEventListener('click', event => {
            const currentButton = event.target.closest('.remove-from-cart-btn');
            if (!currentButton) {
                console.error("Could not find '.remove-from-cart-btn'");
                return;
            }
            const productId = currentButton.dataset.productId;
            const cartItemRow = currentButton.closest('.cart-item');

            if (!productId) {
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

            // Убираем confirm, так как его заменит SweetAlert
            // if (!confirm('Na pewno chcesz usunąc product?')) {
            //     return;
            // }

            Swal.fire({
                title: 'Potwierdź usunięcie',
                text: "Czy na pewno chcesz usunąć ten produkt z koszyka?",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonText: 'Tak, usuń',
                cancelButtonText: 'Anuluj',
                confirmButtonColor: 'var(--color-primary)', // Используем CSS переменную
                cancelButtonColor: 'var(--color-text-medium)', // Используем CSS переменную
            }).then((result) => {
                if (result.isConfirmed) {
                    performDeleteRequest(productId, cartItemRow);
                }
            });
        });
    });

    // --- Обработка изменения количества в input .quantity-input (на странице корзины) ---
    document.querySelectorAll('.quantity-input').forEach(input => {
        input.addEventListener('change', event => {
            const productId = event.target.dataset.productId;
            const newQuantity = parseInt(event.target.value);
            const url = `/store/cart/add/${productId}/`;
            const cartItemRow = event.target.closest('.cart-item');

            if (isNaN(newQuantity) || newQuantity < 0) {
                Toastify({
                    text: 'Proszę wprowadzić poprawną ilość.',
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" } // Исправлено backgroundColor
                }).showToast();
                // Можно вернуть предыдущее значение, если есть способ его сохранить, или значение из cartItemRow
                // event.target.value = event.target.defaultValue; // или какое-то другое значение
                return;
            }

            const formData = new URLSearchParams();
            formData.append('quantity', newQuantity);
            formData.append('update', 'true');

            fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken,
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
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

                    const cartTotalPriceElement = document.getElementById('cart-total-price');
                    if (cartTotalPriceElement) {
                        cartTotalPriceElement.textContent = data.cart_total_price;
                    }

                    updateCartCount(data.cart_total_items);

                    if (data.item_removed) {
                        // Если товар удален (кол-во стало 0), строка будет анимирована и удалена
                        // через performDeleteRequest, если бы мы его вызвали.
                        // Здесь, если сервер удалил товар из-за quantity=0,
                        // мы должны инициировать анимацию удаления строки.
                        if (cartItemRow) {
                            cartItemRow.classList.add('is-removing');
                            cartItemRow.addEventListener('transitionend', () => {
                                cartItemRow.remove();
                            }, { once: true });
                        }
                        if (data.cart_total_items === 0) {
                            setTimeout(() => { window.location.reload(); }, 500);
                        }
                         Toastify({
                            text: "Produkt usunięty (ilość 0).",
                            duration: 3000,
                            gravity: "top",
                            position: "right",
                            style: { background: "linear-gradient(to right, #00b09b, #96c93d)" }
                        }).showToast();

                    } else if (data.quantity_adjusted) {
                        event.target.value = data.adjusted_quantity;
                        Toastify({
                            text: `Ilość produktu "${data.product_name}" poprawiona do ${data.adjusted_quantity} szt. (maksymalna ilość na stanie).`,
                            duration: 5000,
                            gravity: "top",
                            position: "right",
                            style: { background: "linear-gradient(to right, #ff8c00, #ffc371)" } // Исправлено backgroundColor
                        }).showToast();
                    } else {
                        Toastify({
                            text: "Ilość zaktualizowana.",
                            duration: 3000,
                            gravity: "top",
                            position: "right",
                            style: { background: "linear-gradient(to right, #00b09b, #96c93d)" } // Исправлено backgroundColor
                        }).showToast();
                    }
                } else {
                    console.error("Error updating quantity:", data.error || 'Unknown server error');
                    Toastify({
                        text: `Nie udało się zaktualizować ilości: ${data.error || 'Błąd serwera'}`,
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" } // Исправлено backgroundColor
                    }).showToast();
                    // Вернуть старое значение, если есть такая логика и значение сохранено
                }
            })
            .catch(error => {
                console.error('Fetch Error updating quantity:', error);
                Toastify({
                    text: `Błąd przy aktualizacji ilości: ${error.message}`,
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: { background: "linear-gradient(to right, #ff5f6d, #ffc371)" } // Исправлено backgroundColor
                }).showToast();
                 // Вернуть старое значение, если есть такая логика и значение сохранено
            });
        });
    });

}); // Конец DOMContentLoaded