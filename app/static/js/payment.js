(function () {
    "use strict";

    var api = window.apiFetch;


    /* ============================================================
       CONTINUE BUTTON
       ============================================================ */

    var continueBtn = document.getElementById(
        "continuePaymentBtn"
    );

    var paymentError = document.getElementById(
        "paymentError"
    );


    if (continueBtn) {

        continueBtn.addEventListener(
            "click",
            function () {

                /* Prevent double-clicks */
                if (continueBtn.disabled) {
                    return;
                }

                var startUrl =
                    continueBtn.getAttribute(
                        "data-start-url"
                    );

                if (!startUrl) {
                    console.error(
                        "Payment start URL is missing."
                    );

                    return;
                }


                /* ------------------------------------------------
                   Disable button while request is being processed
                   ------------------------------------------------ */

                continueBtn.disabled = true;

                var originalText =
                    continueBtn.textContent;

                continueBtn.textContent =
                    "Sending request...";


                /* Clear previous error */

                if (paymentError) {
                    paymentError.style.display =
                        "none";

                    paymentError.textContent =
                        "";
                }


                /* ------------------------------------------------
                   CALL BACKEND
                   ------------------------------------------------ */

                api(startUrl, {
                    method: "POST"
                })

                .then(function (response) {

                    return response.json()
                        .then(function (data) {

                            return {
                                ok: response.ok,
                                data: data
                            };

                        });

                })

                .then(function (result) {

                    var data = result.data;


                    /* ------------------------------------------------
                       STK PUSH SENT SUCCESSFULLY

                       Flask should return:

                       {
                           "status": "PENDING",
                           "redirect_url": "/processing/..."
                       }
                       ------------------------------------------------ */

                    if (
                        result.ok &&
                        data.redirect_url
                    ) {

                        window.location.href =
                            data.redirect_url;

                        return;
                    }


                    /* ------------------------------------------------
                       BACKEND ERROR
                       ------------------------------------------------ */

                    var message =
                        data.error ||
                        "Unable to send the M-Pesa payment request.";


                    if (paymentError) {

                        paymentError.textContent =
                            message;

                        paymentError.style.display =
                            "block";
                    }


                    continueBtn.disabled = false;

                    continueBtn.textContent =
                        originalText;

                })

                .catch(function (error) {

                    console.error(
                        "Payment initiation error:",
                        error
                    );


                    if (paymentError) {

                        paymentError.textContent =
                            "Unable to start payment. Please try again.";

                        paymentError.style.display =
                            "block";
                    }


                    continueBtn.disabled = false;

                    continueBtn.textContent =
                        originalText;
                });

            }
        );
    }



    /* ============================================================
       PROCESSING SCREEN
       Poll backend until payment reaches a terminal state.
       ============================================================ */

    var card = document.querySelector(
        ".processing-card"
    );


    if (
        card &&
        card.getAttribute("data-poll-url")
    ) {

        var url =
            card.getAttribute(
                "data-poll-url"
            );


        function poll() {

            api(url, {
                method: "GET"
            })

            .then(function (response) {

                return response.json();

            })

            .then(function (data) {


                /* -----------------------------------------------
                   SUCCESS OR FAILURE
                   ----------------------------------------------- */

                if (data.redirect_url) {

                    window.location.href =
                        data.redirect_url;

                    return;
                }


                /* -----------------------------------------------
                   Still pending
                   ----------------------------------------------- */

                window.setTimeout(
                    poll,
                    2500
                );

            })

            .catch(function (error) {

                console.error(
                    "Payment status polling error:",
                    error
                );


                /* Retry after temporary error */

                window.setTimeout(
                    poll,
                    5000
                );

            });
        }


        /* Start polling after 2 seconds */

        window.setTimeout(
            poll,
            2000
        );
    }



    /* ============================================================
       LAB SIMULATION BUTTONS
       ============================================================ */

    Array.prototype.forEach.call(
        document.querySelectorAll(
            "[data-simulate]"
        ),
        function (btn) {

            btn.addEventListener(
                "click",
                function () {

                    btn.disabled = true;


                    api(
                        btn.getAttribute(
                            "data-url"
                        ),
                        {
                            method: "POST",

                            body: {
                                status:
                                    btn.getAttribute(
                                        "data-simulate"
                                    )
                            }
                        }
                    )

                    .then(function (response) {

                        return response.json();

                    })

                    .then(function (data) {

                        if (data.redirect_url) {

                            window.location.href =
                                data.redirect_url;

                            return;
                        }

                        btn.disabled = false;

                    })

                    .catch(function (error) {

                        console.error(
                            "Simulation error:",
                            error
                        );

                        btn.disabled = false;

                    });

                }
            );
        }
    );

})();