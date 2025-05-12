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
             // Простая анимация (можно улучшить)
             cartCountElement.closest('a').style.transform = 'scale(1.2)';
             setTimeout(() => {
                cartCountElement.closest('a').style.transform = 'scale(1)';
             }, 200);
        }
    }

     // --- Обработка кнопки "Добавить в корзину" (УНИВЕРСАЛЬНАЯ) ---
     document.querySelectorAll('.add-to-cart-btn').forEach(button => {
        button.addEventListener('click', event => {
            const btn = event.target;
            const productId = btn.dataset.productId;
            const url = `/cart/add/${productId}/`;

            const formContainer = btn.closest('.add-to-cart-form'); // Ищем родительский контейнер формы на странице деталей
            let quantityInput = null;
            if (formContainer) {
                 quantityInput = formContainer.querySelector('.quantity-input-detail, input[name="quantity"]');
            }

            const quantity = quantityInput ? parseInt(quantityInput.value) : 1;

            if (isNaN(quantity) || quantity <= 0) {
                // ЗАМЕНЕНО НА TOASTIFY (из вашего кода)
                Toastify({
                    text: 'Пожалуйста, введите корректное количество (больше 0).',
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                }).showToast();
                return;
            }

            if (quantityInput && quantity > parseInt(quantityInput.max)) {
                 // ЗАМЕНЕНО НА TOASTIFY (из вашего кода)
                 Toastify({
                    text: `Извините, доступно только ${quantityInput.max} шт.`,
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                }).showToast();
                return;
            }

            const formData = new URLSearchParams();
            formData.append('quantity', quantity);

            btn.disabled = true;
            const originalButtonText = btn.textContent;
            btn.textContent = 'Добавление...';

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
                btn.disabled = false;
                btn.textContent = originalButtonText;
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
                    // ЗАМЕНЕНО НА TOASTIFY (из вашего кода)
                    Toastify({
                        text: "Товар добавлен в корзину!",
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        backgroundColor: "linear-gradient(to right, #00b09b, #96c93d)",
                    }).showToast();
                     if (data.quantity_adjusted && quantityInput) {
                         quantityInput.value = data.adjusted_quantity;
                         // ЗАМЕНЕНО НА TOASTIFY (из вашего кода)
                         Toastify({
                            text: `Количество товара "${data.product_name}" скорректировано до ${data.adjusted_quantity} шт. (максимум на складе).`,
                            duration: 5000,
                            gravity: "top",
                            position: "right",
                            backgroundColor: "linear-gradient(to right, #ff8c00, #ffc371)",
                        }).showToast();
                     }
                } else {
                    console.error("Error adding product:", data.error || 'Unknown error');
                    // ЗАМЕНЕНО НА TOASTIFY (из вашего кода)
                    Toastify({
                        text: `Не удалось добавить товар: ${data.error || 'Произошла ошибка'}`,
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                    }).showToast();
                }
            })
            .catch(error => {
                 btn.disabled = false;
                 btn.textContent = originalButtonText;
                console.error('Fetch Error:', error);
                // ЗАМЕНЕНО НА TOASTIFY (из вашего кода)
                Toastify({
                    text: `Произошла ошибка при добавлении товара: ${error.message}`,
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                }).showToast();
            });
        });
    });

    // --- Обработка кнопки "Удалить" (на странице корзины) ---
     document.querySelectorAll('.remove-from-cart-btn').forEach(button => {
        button.addEventListener('click', event => {
            const productId = event.target.dataset.productId;
            const url = `/cart/remove/${productId}/`;
            const cartItemRow = event.target.closest('.cart-item');

            if (!confirm('Вы уверены, что хотите удалить этот товар?')) { // Оставили confirm()
                return;
            }

            fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => {
                 if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
             })
            .then(data => {
                if (data.status === 'ok') {
                    console.log(`Product ${productId} removed from cart.`);
                    if (cartItemRow) {
                        cartItemRow.remove();
                    }
                    updateCartCount(data.cart_total_items);
                    const totalPriceElement = document.getElementById('cart-total-price');
                    if (totalPriceElement) {
                        totalPriceElement.textContent = data.cart_total_price;
                    }
                    if (data.cart_total_items === 0) {
                        window.location.reload();
                    }
                    // Сообщение об успешном удалении (можно добавить Toastify и сюда)
                    Toastify({
                        text: "Товар удален из корзины.",
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        backgroundColor: "linear-gradient(to right, #00b09b, #96c93d)", // Зеленый для успеха
                    }).showToast();
                } else {
                    console.error("Error removing product:", data);
                    // alert('Не удалось удалить товар.'); // <--- ЗАМЕНЯЕМ
                    Toastify({
                        text: `Не удалось удалить товар: ${data.error || 'Произошла ошибка'}`,
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                    }).showToast();
                }
            })
            .catch(error => {
                console.error('Fetch Error:', error);
                // alert('Произошла ошибка при удалении товара.'); // <--- ЗАМЕНЯЕМ
                Toastify({
                    text: `Произошла ошибка при удалении товара: ${error.message}`,
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                }).showToast();
            });
        });
    });

    // --- Обработка изменения количества в input .quantity-input (на странице корзины) ---
    document.querySelectorAll('.quantity-input').forEach(input => {
        input.addEventListener('change', event => {
            const productId = event.target.dataset.productId;
            const newQuantity = parseInt(event.target.value);
            // const maxQuantity = parseInt(event.target.max); // Мы убрали эту клиентскую проверку в вашем коде
            const url = `/cart/add/${productId}/`;
            const cartItemRow = event.target.closest('.cart-item');

            if (isNaN(newQuantity) || newQuantity < 0) { // Оставим newQuantity < 0, т.к. сервер обработает удаление при 0
                // alert('Пожалуйста, введите корректное количество.'); // <--- ЗАМЕНЯЕМ
                Toastify({
                    text: 'Пожалуйста, введите корректное количество.',
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                }).showToast();
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
                         cartItemRow.remove();
                         if (data.cart_total_items === 0) {
                             window.location.reload();
                         }
                     } else if (data.quantity_adjusted) {
                         event.target.value = data.adjusted_quantity;
                         // alert(`Количество товара "${data.product_name}" скорректировано...`); // <--- ЗАМЕНЯЕМ
                         Toastify({
                            text: `Количество товара "${data.product_name}" скорректировано до ${data.adjusted_quantity} шт. (максимум на складе).`,
                            duration: 5000,
                            gravity: "top",
                            position: "right",
                            backgroundColor: "linear-gradient(to right, #ff8c00, #ffc371)", // Оранжевый для предупреждения
                        }).showToast();
                     } else {
                         // Если просто успешно обновили, можно тоже показать уведомление
                         Toastify({
                            text: "Количество товара обновлено.",
                            duration: 3000,
                            gravity: "top",
                            position: "right",
                            backgroundColor: "linear-gradient(to right, #00b09b, #96c93d)",
                        }).showToast();
                     }

                } else {
                    console.error("Error updating quantity:", data.error || 'Unknown error');
                    // ЗАМЕНЕНО НА TOASTIFY (из вашего кода)
                    Toastify({
                        text: `Не удалось обновить количество: ${data.error || 'Произошла ошибка'}`,
                        duration: 3000, // Добавил длительность по умолчанию
                        gravity: "top", // Добавил по умолчанию
                        position: "right", // Добавил по умолчанию
                        backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                    }).showToast();
                }
            })
            .catch(error => {
                console.error('Fetch Error:', error);
                // ЗАМЕНЕНО НА TOASTIFY (из вашего кода)
                Toastify({
                    text: `Произошла ошибка при обновлении количества: ${error.message}`,
                    duration: 3000, // Добавил длительность по умолчанию
                    gravity: "top", // Добавил по умолчанию
                    position: "right", // Добавил по умолчанию
                    backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                }).showToast();
            });
        });
    });
});