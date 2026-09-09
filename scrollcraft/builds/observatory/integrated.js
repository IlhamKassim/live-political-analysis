'use strict';
(() => {
  window.ScrollCraft?.mount(document.querySelector('main'));

  const root = document.documentElement;
  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
  let paused = motionQuery.matches;
  let queued = false;

  const updateMotion = () => {
    root.classList.toggle('motion-off', paused);
    root.classList.toggle('js-motion', !paused);
    document.querySelectorAll('.motion-control').forEach((button) => {
      button.textContent = paused ? 'Enable motion' : 'Pause motion';
      button.setAttribute('aria-pressed', String(paused));
    });
    window.dispatchEvent(new Event('motionchange'));
  };

  window.motionPaused = () => paused;
  document.querySelectorAll('.motion-control').forEach((button) => {
    button.addEventListener('click', () => {
      paused = !paused;
      updateMotion();
    });
  });
  motionQuery.addEventListener('change', (event) => {
    paused = event.matches;
    updateMotion();
  });
  updateMotion();

  const revealObserver = new IntersectionObserver(
    (entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-in');
        revealObserver.unobserve(entry.target);
      }
    }),
    { threshold: 0.12 },
  );
  document.querySelectorAll('.flow-reveal').forEach((element) => revealObserver.observe(element));

  const words = [...document.querySelectorAll('.word-ink')];
  words.forEach((element) => {
    const copy = element.textContent.trim();
    element.setAttribute('aria-label', copy);
    element.textContent = '';
    copy.split(/\s+/).forEach((word) => {
      const span = document.createElement('span');
      span.textContent = `${word} `;
      span.setAttribute('aria-hidden', 'true');
      element.append(span);
    });
  });

  const hero = document.querySelector('.hero');
  const city = document.querySelector('.city-plane');
  const copy = document.querySelector('.hero-copy');
  const orbit = document.querySelector('.sky-orbit');
  const act = document.querySelector('.chamber-act');
  const number = document.querySelector('.chamber-number');
  const circles = [...document.querySelectorAll('.seat-dot')].map((element) => ({
    element,
    x: Number(element.dataset.x),
    y: Number(element.dataset.y),
    tx: Number(element.dataset.tx),
    ty: Number(element.dataset.ty),
  }));
  const clamp = (value) => Math.max(0, Math.min(1, value));

  function render() {
    queued = false;
    const scrollTop = Math.min(scrollY, hero?.offsetHeight ?? 0);
    if (city) city.style.transform = paused ? 'none' : `translate3d(0, ${scrollTop * 0.2}px, 0)`;
    if (copy) copy.style.transform = paused ? 'none' : `translate3d(0, ${scrollTop * 0.07}px, 0)`;
    if (orbit) orbit.style.transform = paused ? 'none' : `translate3d(0, ${scrollTop * 0.32}px, 0)`;

    if (act && circles.length) {
      const box = act.getBoundingClientRect();
      const span = Math.max(1, act.offsetHeight - innerHeight);
      const progress = paused ? 1 : clamp(-box.top / span);
      const phase = clamp(progress * 1.7);
      const smooth = phase * phase * (3 - 2 * phase);
      circles.forEach((circle, index) => {
        const amount = paused ? 1 : clamp((smooth - index / circles.length * 0.1) / 0.9);
        circle.element.setAttribute('cx', String(circle.x + (circle.tx - circle.x) * amount));
        circle.element.setAttribute('cy', String(circle.y + (circle.ty - circle.y) * amount));
      });
      if (number) number.style.opacity = String(clamp((progress - 0.45) * 4));
    }

    const max = document.documentElement.scrollHeight - innerHeight;
    document.querySelector('.progress-line')?.style.setProperty(
      'transform',
      `scaleX(${max ? scrollY / max : 0})`,
    );
    words.forEach((element) => {
      const box = element.getBoundingClientRect();
      const progress = clamp((innerHeight * 0.87 - box.top) / (innerHeight * 0.6));
      [...element.children].forEach((word, index) => {
        word.classList.toggle('lit', paused || progress > index / element.children.length);
      });
    });
  }

  const schedule = () => {
    if (!queued) {
      queued = true;
      requestAnimationFrame(render);
    }
  };
  addEventListener('scroll', schedule, { passive: true });
  addEventListener('resize', schedule);
  addEventListener('motionchange', schedule);

  const menuToggle = document.querySelector('.menu-toggle');
  const navigation = document.querySelector('.nav-links');
  menuToggle?.addEventListener('click', () => {
    const open = navigation?.classList.toggle('is-open') ?? false;
    menuToggle.setAttribute('aria-expanded', String(open));
  });
  navigation?.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
    navigation.classList.remove('is-open');
    menuToggle?.setAttribute('aria-expanded', 'false');
  }));
  addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      navigation?.classList.remove('is-open');
      menuToggle?.setAttribute('aria-expanded', 'false');
    }
  });

  const majorityToggle = document.querySelector('#majority-toggle');
  majorityToggle?.addEventListener('click', () => {
    const active = majorityToggle.getAttribute('aria-pressed') !== 'true';
    majorityToggle.setAttribute('aria-pressed', String(active));
    document.querySelector('#seat-assembly')?.classList.toggle('show-majority', active);
    const note = document.querySelector('#majority-note');
    if (note) note.textContent = active ? '112 highlighted Seats. Enough for a Majority.' : '112 Seats make a Majority.';
  });

  render();
})();
