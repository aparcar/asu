const fs = require("fs");

let rawdata = fs.readFileSync("tests/regressions/regression-gh1176.json");
let request_json = JSON.parse(rawdata);
let url = "https://sysupgrade.openwrt.org";

async function do_request(data) {
  request = {
    packages: data.packages,
    target: data.target,
    version: data.version,
    profile: data.profile,
  };

  return fetch(url + "/api/v1/build", {
    method: "POST",
    mode: "cors",
    cache: "no-cache",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
    },
    redirect: "follow",
    referrerPolicy: "no-referrer",
    body: JSON.stringify(request),
  }).then((response) => response.json());
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function run() {
  while (true) {
    const foo = await do_request(request_json);
    console.log(foo);
    if (foo.status != 202) {
      return;
    }
    await sleep(1000);
  }
}

run();
