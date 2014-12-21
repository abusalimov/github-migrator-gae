function handleState(state) {
	window.initialState = state;
}

function initAjaxHrefs(selector, handler, wait_selector) {
	$(selector).click(function(e) {
		e.preventDefault();
		var $link = $(this)
		return $.ajax({
			dataType: "json",
			url: $link.attr('href'),
			beforeSend: function() {
				if (wait_selector !== undefined) {
					$link.css('visibility', 'hidden');
					$(wait_selector).show();
				}
			},
			complete: function() {
				if (wait_selector !== undefined) {
					$link.css('visibility', 'visible');
					$(wait_selector).hide();
				}
			},
			success: handler,
		});
	});
}

$(document).ready(function (e) {
	var $debug             = $('#debug');
	var $error             = $('#error');
	var $errorMessage      = $('#error-message')
	var $auth              = $('#auth');

	var $user              = $('#user');
	var $userName          = $('#user-name');
	var $userId            = $('#user-id');
	var $userLogin         = $('#user-login');
	var $userLink          = $('#user-link');
	var $userPicture       = $('#user-picture');
	var $userEmails        = $('#user-emails');
	var $userHasEmails     = $('.user-has-emails')
	var $userHasNoEmails   = $('.user-has-no-emails')
	var $userHasManyEmails = $('.user-has-many-emails');
	var $userEmailTemplate = $.templates('#user-email-template');

	function hideError(e) {
		$error.slideUp('fast');
	}
	$('#error .close, a.authomatic, a.ajax').click(hideError);

	function realHandleState(state) {
		$debug.html(JSON.stringify(state, undefined, 4));

		user = state.user;

		$user.toggle(!!user);
		$auth.toggle(!user);

		if (state.error) {
			$errorMessage.html(state.error.message);
			$error.show();
		} else {
			hideError();
		}

		if (user) {
			info = user.info;

			$userName.html(info.name);
			$userId.html(info.id);
			$userLogin.html(info.username);
			$userLink.attr('href', info.link);
			$userPicture.attr('src', info.picture);

			emails = $.map(user.emails, function(email) {
				return {email: email, emailUrl: encodeURI(email)};
			});

			$userEmails.html($userEmailTemplate.render(emails));
			initAjaxHrefs('#user-emails a.ajax', realHandleState,
				'#user-emails .spinner');

			$userHasEmails.toggle(emails.length != 0);
			$userHasNoEmails.toggle(emails.length == 0);
			$userHasManyEmails.toggle(emails.length > 1);
		}
	}
	window.handleState = realHandleState;

	authomatic.setup({
		backend: '/app/login/',
		onLoginComplete: realHandleState,
		popupWidth: 1040,  // github
		popupHeight: 660,
	});

	authomatic.popupInit();
	initAjaxHrefs('a.ajax', realHandleState);

	if (typeof initialState !== 'undefined') {
		realHandleState(initialState);
	}
});
