document.addEventListener('DOMContentLoaded', () => {
  const links = Array.from(document.querySelectorAll('.nav-list a'));
  links.forEach((link) => {
    if (window.location.pathname.includes(link.getAttribute('href'))) {
      link.style.background = 'rgba(255,255,255,0.18)';
    }
  });
});
