async (page) => {
  // Observation scenario: delay unchanged bytes of one real pre-join GET.
  // This is not a regression asserting desired behaviour.
  const api = 'http://127.0.0.1:18280';
  const url = 'http://127.0.0.1:18281/course/review-c01/group/4431/lab/' + encodeURIComponent('ЛР1');
  const reset = await page.request.post(api + '/__harness__/reset');
  if (reset.status() !== 200) throw new Error('Synthetic fixture reset failed');
  await page.context().clearCookies();
  await page.goto(url);
  await page.getByRole('textbox', { name: 'Фамилия' }).fill('Иванов');
  await page.getByRole('textbox', { name: 'Имя', exact: true }).fill('Иван');
  await page.getByRole('textbox', { name: 'Отчество' }).fill('Иванович');
  await page.getByRole('textbox', { name: 'GitHub' }).fill('review-ivanov');
  await page.getByRole('button', { name: 'Записаться', exact: true }).waitFor();

  let release;
  let captured;
  const gate = new Promise(resolve => { release = resolve; });
  const ready = new Promise(resolve => { captured = resolve; });
  let held = false;
  let delayedBody;
  const handler = async route => {
    if (!held && route.request().method() === 'GET') {
      held = true;
      const response = await route.fetch();
      const body = await response.body();
      delayedBody = JSON.parse(body.toString());
      captured();
      await gate;
      await route.fulfill({ response, body });
    } else {
      await route.continue();
    }
  };
  await page.route('**/queue', handler);
  try {
    await page.getByRole('button', { name: 'Обновить', exact: true }).click();
    await ready;
    await page.getByRole('button', { name: 'Записаться', exact: true }).click();
    await page.getByText('Вы записаны в очередь.', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Выйти из очереди', exact: true }).waitFor();
    const afterJoin = await page.locator('section').innerText();
    release();
    await page.getByRole('button', { name: 'Записаться', exact: true }).waitFor();
    const afterOldRead = await page.locator('section').innerText();
    const stateResponse = await page.request.get(api + '/__harness__/state');
    const state = await stateResponse.json();
    const row = state.queue.find(item => item['ФИО'] === 'Иванов Иван Иванович');
    if (!row || row['Статус'] !== 'ждёт') throw new Error('No stored waiting row: not the stale-view scenario');
    if (!afterOldRead.includes('Вы записаны в очередь.') || afterOldRead.includes('Иванов Иван Иванович')) {
      throw new Error('Stale display not observed; do not label this reproduction successful');
    }
    await page.unroute('**/queue', handler);
    await page.getByRole('button', { name: 'Обновить', exact: true }).click();
    await page.getByRole('button', { name: 'Выйти из очереди', exact: true }).waitFor();
    const afterRefresh = await page.locator('section').innerText();
    return {
      kind: 'scenario',
      intervention: 'Delayed one real pre-join GET /queue until post-join reload rendered; response bytes unchanged',
      delayedBody,
      afterJoin,
      afterOldRead,
      storedQueue: state.queue,
      afterRefresh,
      limits: 'Pinned real frontend/backend routes; synthetic Sheets/GitHub/CI/window. Managed network ordering, not proof of the colleague original latency cause. No tokens/headers retained.'
    };
  } finally {
    release();
    await page.unroute('**/queue', handler);
  }
}
